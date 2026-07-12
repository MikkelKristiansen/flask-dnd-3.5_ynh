;;; dnd-adventure-mode.el --- Skrivestøtte til D&D 3.5-eventyr (adventure.md) -*- lexical-binding: t; -*-

;; Author: flask-dnd-3.5
;; Version: 2 (v2: + buffer-completion, eldoc, hop-til-def, flymake-lint, snippets)
;; Package-Requires: ((emacs "29.1") (markdown-mode "2.5"))
;; Keywords: games, wp

;;; Commentary:

;; Major mode oven på `markdown-mode' til at forfatte eventyr i det format
;; `dm_parser.py' læser (# scene, ## Rum:/## Kort:/## Statblok:, @type[id],
;; ## Monstre-rosters, > read-aloud).  v1 giver:
;;
;;   * Syntaks-fremhævning af @type[id] og de strukturelle ## -overskrifter.
;;   * Completion-at-point: skriv "@monster[" og få alle monster-id'er fra
;;     srd35.db (samme normaliserede indeks som appen bruger — ingen YAML
;;     genparsing, ingen kørende Flask).  Emacs 29+ læser SQLite indbygget.
;;   * M-x dnd-insert-monster: vælg et monster ved NAVN → indsæt @monster[id].
;;
;; v2 lægger dokument-lokal støtte oveni (spejler `dm_parser's to-lags model —
;; monster fra db, npc/kort/brev fra selve bufferen):
;;
;;   * Completion af @npc[/@kort[/@brev[ fra bufferens `## Statblok:'/`## Kort:'/
;;     `## Brev:'-overskrifter (id'et slugificeres som i appen).
;;   * Eldoc: punkt på @monster[…] → én linje (navn · CR · HP · AC · angreb);
;;     punkt på @npc[…] → titel + første linje af dens `## Statblok:'-blok.
;;   * C-c C-d .  (dnd-goto-definition): hop til definitionen — buffer-overskrift
;;     for lokale typer, ellers `sources/data/monsters.yaml' for monstre.
;;   * Flymake: markér referencer der ikke resolver (ukendt monster-id eller en
;;     lokal reference uden matchende `## …:'-overskrift).  @faelde[…] lintes ikke.
;;   * Snippets (hvis yasnippet er indlæst): scene / rum / roster / statblok /
;;     ra (read-aloud) / brev / kort — spejler `adventures/_TEMPLATE.md'.
;;
;; Data-kilden er `srd35.db'.  Den lokaliseres automatisk ved at gå op fra den
;; åbne fil til repoets rod (mappen der indeholder `sources/'); ellers sæt
;; `dnd-adventure-db-path' manuelt.
;;
;; Installation (i din init):
;;
;;   (add-to-list 'load-path "/sti/til/flask-dnd-3.5/editor")
;;   (require 'dnd-adventure-mode)
;;   (add-to-list 'auto-mode-alist
;;                '("/adventures/.*/adventure\\.md\\'" . dnd-adventure-mode))

;;; Code:

(require 'markdown-mode)
(require 'flymake)
(require 'json)

;; Db-browseren lever i sin egen fil (klart adskilt ansvar) og requirer DENNE
;; fil for db-path-helperen — autoload for at undgå cirkulær require.
(autoload 'dnd-browse "dnd-browse" "Browse referencebanken i srd35.db." t)

;; yasnippet er valgfrit — deklarér symbolerne så byte-compile forbliver rent,
;; uden at gøre pakken til en hård afhængighed.
(defvar yas-snippet-dirs)
(declare-function yas-load-directory "yasnippet")
(declare-function yas-minor-mode "yasnippet")

(defgroup dnd-adventure nil
  "Skrivestøtte til D&D 3.5-eventyr."
  :group 'text
  :prefix "dnd-adventure-")

(defcustom dnd-adventure-db-path nil
  "Sti til srd35.db.  Nil = lokalisér automatisk (op til mappen med `sources/')."
  :type '(choice (const :tag "Automatisk" nil) file)
  :group 'dnd-adventure)

(defface dnd-entity-type-face '((t :inherit font-lock-keyword-face))
  "Face for @type-delen af en entity-reference."
  :group 'dnd-adventure)

(defface dnd-entity-id-face '((t :inherit font-lock-constant-face))
  "Face for id-delen inde i @type[id]."
  :group 'dnd-adventure)

(defface dnd-structural-face '((t :inherit font-lock-type-face :weight bold))
  "Face for strukturelle ##-overskrifter (Rum/Kort/Statblok…)."
  :group 'dnd-adventure)

;; ── Data: srd35.db ──────────────────────────────────────────────────────────

(defvar dnd-adventure--monster-cache nil
  "Cachet alist (ID . NAVN) over monstre.  Nulstil med `dnd-refresh-data'.")

(defun dnd-adventure--db-path ()
  "Find srd35.db: eksplicit indstilling → op fra filen til repo-rod → cwd."
  (or (and dnd-adventure-db-path (expand-file-name dnd-adventure-db-path))
      (let ((root (and buffer-file-name
                       (locate-dominating-file buffer-file-name "sources"))))
        (and root (expand-file-name "sources/srd35.db" root)))
      (expand-file-name "srd35.db" default-directory)))

(defun dnd-adventure--query-monsters ()
  "Læs (ID . NAVN) for alle monstre fra srd35.db.  Signalér en klar fejl ellers."
  (unless (and (fboundp 'sqlite-available-p) (sqlite-available-p))
    (user-error "Denne Emacs har ikke indbygget SQLite (kræver Emacs 29+)"))
  (let ((path (dnd-adventure--db-path)))
    (unless (file-exists-p path)
      (user-error "srd35.db ikke fundet: %s — kør `python importer.py'" path))
    (let ((db (sqlite-open path)))
      (unwind-protect
          (mapcar (lambda (row) (cons (nth 0 row) (nth 1 row)))
                  (sqlite-select db "SELECT id, name FROM monsters ORDER BY name"))
        (sqlite-close db)))))

(defun dnd-adventure--monsters ()
  "Cachet alist (ID . NAVN) over monstre."
  (or dnd-adventure--monster-cache
      (setq dnd-adventure--monster-cache (dnd-adventure--query-monsters))))

(defun dnd-adventure--db-query (sql &rest params)
  "Kør SQL mod srd35.db med PARAMS og returnér rækkerne (liste af lister).
Returnér nil hvis SQLite/db ikke er tilgængelig — kaldere linter/eldoc'er blødt."
  (when (and (fboundp 'sqlite-available-p) (sqlite-available-p))
    (let ((path (dnd-adventure--db-path)))
      (when (file-exists-p path)
        (let ((db (sqlite-open path)))
          (unwind-protect
              (sqlite-select db sql params)
            (sqlite-close db)))))))

(defun dnd-adventure--monster-ids ()
  "Hash-sæt af gyldige monster-id'er (til lint).  Nil hvis db utilgængelig."
  (when (or dnd-adventure--monster-cache
            (ignore-errors (dnd-adventure--monsters)))
    (let ((h (make-hash-table :test 'equal)))
      (dolist (m dnd-adventure--monster-cache h)
        (puthash (car m) t h)))))

;;;###autoload
(defun dnd-refresh-data ()
  "Glem cachet SRD-data (efter en `python importer.py')."
  (interactive)
  (setq dnd-adventure--monster-cache nil)
  (message "D&D-data genindlæses ved næste opslag."))

;; ── Dokument-lokale definitioner (npc/kort/brev fra bufferen) ────────────────

(defconst dnd-adventure--local-types
  '(("npc"  . "Statblok")
    ("kort" . "Kort")
    ("brev" . "Brev"))
  "Ref-TYPE → den `## <ORD>:'-overskrift der definerer den i bufferen.
Spejler `dm_parser': @npc[…] resolves mod `## Statblok:' (statblok-opslag er
type-uafhængigt), @kort[…] mod `## Kort:', @brev[…] mod `## Brev:'.")

(defun dnd-adventure--slugify (text)
  "Port af `dm_parser.slugify' 1:1: lowercase, æ→ae ø→oe å→aa,
alt ikke-alfanumerisk → \"-\", trim ledende/afsluttende \"-\"."
  (let* ((s (downcase (string-trim text)))
         (s (replace-regexp-in-string "æ" "ae" s t t))
         (s (replace-regexp-in-string "ø" "oe" s t t))
         (s (replace-regexp-in-string "å" "aa" s t t))
         (s (replace-regexp-in-string "[^a-z0-9]+" "-" s)))
    (replace-regexp-in-string "\\`-+\\|-+\\'" "" s)))

(defun dnd-adventure--heading-regexp (heading)
  "Regexp der matcher `## HEADING: <titel>' (præcis to #, som `dm_parser')."
  (concat "^## +" (regexp-quote heading) ":[ \t]*\\(.+?\\)[ \t]*$"))

(defun dnd-adventure--buffer-defs (heading)
  "Scan bufferen for `## HEADING: Titel' og returnér en alist (ID . TITEL).
ID slugificeres som appen (`dnd-adventure--slugify'), så buffer-defs matcher
det appens id-resolution giver."
  (let ((re (dnd-adventure--heading-regexp heading))
        (case-fold-search t)
        (defs '()))
    (save-excursion
      (goto-char (point-min))
      (while (re-search-forward re nil t)
        (let ((title (match-string-no-properties 1)))
          (push (cons (dnd-adventure--slugify title) title) defs))))
    (nreverse defs)))

;; ── Completion-at-point ─────────────────────────────────────────────────────

(defun dnd-adventure--entity-context ()
  "Hvis punktet står inde i @type[…], returnér (TYPE START END).
START/END afgrænser id-teksten der skal completes (fra efter [ til punktet)."
  (save-excursion
    (let ((orig (point))
          (bol (line-beginning-position)))
      (when (re-search-backward "@\\([A-Za-zÆØÅæøå]+\\)\\[" bol t)
        (let ((type (downcase (match-string-no-properties 1)))
              (start (match-end 0)))
          ;; Stadig inde i klammen? (intet ] mellem [ og punktet)
          (goto-char start)
          (when (and (>= orig start)
                     (not (re-search-forward "\\]" orig t)))
            (list type start orig)))))))

(defun dnd-adventure--used-ids (type)
  "Reference-harvest: id'er der ALLEREDE er brugt i @TYPE[…] i bufferen.
For typer uden def-blok (fx faelde) — foreslår tidligere brugte id'er igen."
  (let ((re (concat "@" (regexp-quote type) "\\[\\([^]\n]+\\)\\]"))
        (seen (make-hash-table :test 'equal))
        (ids '()))
    (save-excursion
      (goto-char (point-min))
      (while (re-search-forward re nil t)
        (let ((id (match-string-no-properties 1)))
          (unless (gethash id seen)
            (puthash id t seen)
            (push (cons id "(brugt)") ids)))))
    (nreverse ids)))

(defun dnd-adventure--candidates (type)
  "Alist (ID . ANNOTATION) for entity-TYPE.
Monster kommer fra srd35.db (v1); npc/kort/brev fra bufferens
`## …:'-overskrifter; øvrige typer (fx faelde) reference-harvestes
fra tidligere brug i bufferen."
  (let ((heading (cdr (assoc type dnd-adventure--local-types))))
    (cond
     ((string= type "monster") (dnd-adventure--monsters))
     (heading (dnd-adventure--buffer-defs heading))
     (t (dnd-adventure--used-ids type)))))

(defun dnd-adventure-completion-at-point ()
  "`completion-at-point-functions'-indgang for @type[id]-referencer."
  (let ((ctx (dnd-adventure--entity-context)))
    (when ctx
      (let* ((type (nth 0 ctx))
             (start (nth 1 ctx))
             (end (nth 2 ctx))
             (defs (dnd-adventure--candidates type)))
        (when defs
          (list start end (mapcar #'car defs)
                :exclusive 'no
                :annotation-function
                (lambda (id)
                  (let ((label (cdr (assoc id defs))))
                    (and label (concat "  " label))))))))))

;; ── Indsæt via navn ─────────────────────────────────────────────────────────

;;;###autoload
(defun dnd-insert-monster ()
  "Vælg et monster ved NAVN og indsæt @monster[id] ved punktet."
  (interactive)
  (let* ((monsters (dnd-adventure--monsters))
         (choices (mapcar (lambda (m)
                            (cons (format "%s  (%s)" (cdr m) (car m)) (car m)))
                          monsters))
         (pick (completing-read "Monster: " choices nil t))
         (id (cdr (assoc pick choices))))
    (when id (insert (format "@monster[%s]" id)))))

;; ── Reference ved punktet (delt af eldoc, hop-til-def) ───────────────────────

(defun dnd-adventure--ref-at-point ()
  "Hvis punktet er på en @type[id]-reference, returnér (TYPE ID BEG END)."
  (save-excursion
    (let ((p (point)) result)
      (beginning-of-line)
      (while (and (not result)
                  (re-search-forward
                   "@\\([A-Za-zÆØÅæøå]+\\)\\[\\([^]\n]+\\)\\]"
                   (line-end-position) t))
        (when (and (>= p (match-beginning 0)) (<= p (match-end 0)))
          (setq result (list (downcase (match-string-no-properties 1))
                             (match-string-no-properties 2)
                             (match-beginning 0) (match-end 0)))))
      result)))

(defun dnd-adventure--local-def-position (type id)
  "Linjestart for `## <heading>: <titel>' hvor slug(titel)=ID for TYPE.
Nil hvis ingen matchende overskrift i bufferen."
  (let ((heading (cdr (assoc type dnd-adventure--local-types))))
    (when heading
      (let ((re (dnd-adventure--heading-regexp heading))
            (case-fold-search t))
        (save-excursion
          (goto-char (point-min))
          (catch 'found
            (while (re-search-forward re nil t)
              (when (equal (dnd-adventure--slugify (match-string-no-properties 1)) id)
                (throw 'found (match-beginning 0))))
            nil))))))

;; ── Eldoc-preview ────────────────────────────────────────────────────────────

(defun dnd-adventure--first-attack (json)
  "Formatér første angreb fra en attacks-JSON-streng, ellers nil."
  (when (and (stringp json) (> (length json) 0))
    (let ((arr (ignore-errors
                 (json-parse-string json :object-type 'alist :array-type 'list))))
      (when (consp arr)
        (let* ((a (car arr))
               (name (alist-get 'name a))
               (bonus (alist-get 'bonus a))
               (dmg (alist-get 'damage a)))
          (when name
            (concat name
                    (and bonus (format " %s" bonus))
                    (and dmg (format " (%s)" dmg)))))))))

(defun dnd-adventure--monster-eldoc (id)
  "Én-linjes eldoc for @monster[ID] fra srd35.db."
  (let ((rows (dnd-adventure--db-query
               "SELECT name, cr, hp_max, ac, attacks FROM monsters WHERE id = ?"
               id)))
    (when rows
      (let* ((r (car rows))
             (atk (dnd-adventure--first-attack (nth 4 r))))
        (concat (propertize (nth 0 r) 'face 'bold)
                (format " · CR %s · HP %s · AC %s"
                        (or (nth 1 r) "?") (nth 2 r) (nth 3 r))
                (and atk (concat " · " atk)))))))

(defun dnd-adventure--local-eldoc (type id)
  "Eldoc for en dokument-lokal reference: titel + første linje af dens blok."
  (let ((pos (dnd-adventure--local-def-position type id)))
    (when pos
      (save-excursion
        (goto-char pos)
        (looking-at (dnd-adventure--heading-regexp
                     (cdr (assoc type dnd-adventure--local-types))))
        (let ((title (match-string-no-properties 1))
              (first ""))
          (forward-line 1)
          ;; Hop tomme linjer og ```-fences over til første indholdslinje.
          (while (and (not (eobp))
                      (not (looking-at "^## "))
                      (let ((l (string-trim (thing-at-point 'line t))))
                        (or (string-empty-p l) (string-prefix-p "```" l))))
            (forward-line 1))
          (when (and (not (eobp)) (not (looking-at "^## ")))
            (setq first (string-trim (thing-at-point 'line t))))
          (concat (propertize (or title id) 'face 'bold)
                  (unless (string-empty-p first) (concat " · " first))))))))

(defun dnd-adventure-eldoc (callback &rest _)
  "eldoc-`documentation-function': forklar @type[id]-referencen ved punktet."
  (let ((ref (dnd-adventure--ref-at-point)))
    (when ref
      (let* ((type (nth 0 ref)) (id (nth 1 ref))
             (doc (cond
                   ((string= type "monster") (dnd-adventure--monster-eldoc id))
                   ((assoc type dnd-adventure--local-types)
                    (dnd-adventure--local-eldoc type id)))))
        (when doc (funcall callback doc) t)))))

;; ── Hop-til-definition ───────────────────────────────────────────────────────

(defun dnd-adventure--goto-monster (id)
  "Åbn `sources/data/monsters.yaml' og hop til `id: ID'-linjen."
  (let* ((root (and buffer-file-name
                    (locate-dominating-file buffer-file-name "sources")))
         (yaml (and root (expand-file-name "sources/data/monsters.yaml" root))))
    (unless (and yaml (file-exists-p yaml))
      (user-error "monsters.yaml ikke fundet (søgt fra %s)"
                  (or buffer-file-name default-directory)))
    (find-file yaml)
    (goto-char (point-min))
    (if (re-search-forward
         (concat "^[-# \t]*id:[ \t]*" (regexp-quote id) "[ \t]*$") nil t)
        (progn (beginning-of-line) (recenter 0))
      (message "Monster-id %s ikke fundet i monsters.yaml" id))))

;;;###autoload
(defun dnd-goto-definition ()
  "Hop til definitionen af @type[id]-referencen ved punktet.
Lokale typer (npc/kort/brev) → matchende `## …:'-overskrift i bufferen;
monster → `sources/data/monsters.yaml' på posten."
  (interactive)
  (let ((ref (dnd-adventure--ref-at-point)))
    (unless ref (user-error "Punktet står ikke på en @type[id]-reference"))
    (let ((type (nth 0 ref)) (id (nth 1 ref)))
      (cond
       ((assoc type dnd-adventure--local-types)
        (let ((pos (dnd-adventure--local-def-position type id)))
          (unless pos
            (user-error "Ingen `## %s:'-definition for %s i bufferen"
                        (cdr (assoc type dnd-adventure--local-types)) id))
          (push-mark)
          (goto-char pos)
          (recenter 0)))
       ((string= type "monster") (dnd-adventure--goto-monster id))
       (t (user-error "@%s[…] har ingen definition at hoppe til" type))))))

;; ── Flymake-lint ─────────────────────────────────────────────────────────────

(defun dnd-adventure--flymake (report-fn &rest _)
  "Flymake-backend: markér @type[id]-referencer der ikke resolver.
Monster tjekkes mod db-id-sættet; npc/kort/brev mod bufferens definitioner;
faelde og ukendte typer lintes ikke.  Db utilgængelig → monster-lint
droppes blødt (ingen falske fejl)."
  (let ((monster-ids (ignore-errors (dnd-adventure--monster-ids)))
        (defs-cache (make-hash-table :test 'equal))
        (diags '()))
    (save-excursion
      (goto-char (point-min))
      (while (re-search-forward
              "@\\([A-Za-zÆØÅæøå]+\\)\\[\\([^]\n]+\\)\\]" nil t)
        (let* ((type (downcase (match-string-no-properties 1)))
               (id (match-string-no-properties 2))
               (beg (match-beginning 2))
               (end (match-end 2))
               (heading (cdr (assoc type dnd-adventure--local-types)))
               (bad nil))
          (cond
           ((string= type "monster")
            (when (and monster-ids (not (gethash id monster-ids)))
              (setq bad (format "Ukendt monster-id: %s" id))))
           (heading
            (let ((ids (or (gethash type defs-cache)
                           (puthash type
                                    (let ((h (make-hash-table :test 'equal)))
                                      (dolist (d (dnd-adventure--buffer-defs heading) h)
                                        (puthash (car d) t h)))
                                    defs-cache))))
              (unless (gethash id ids)
                (setq bad (format "Ingen `## %s:'-definition for %s" heading id))))))
          (when bad
            (push (flymake-make-diagnostic (current-buffer) beg end :warning bad)
                  diags)))))
    (funcall report-fn (nreverse diags))))

;; ── Font-lock ───────────────────────────────────────────────────────────────

(defconst dnd-adventure--font-lock-keywords
  (list
   ;; @type[id] — type og id hver sin farve (override markdown).
   (list "\\(@[A-Za-zÆØÅæøå]+\\)\\(\\[\\)\\([^]\n]+\\)\\(\\]\\)"
         '(1 'dnd-entity-type-face t)
         '(3 'dnd-entity-id-face t))
   ;; Strukturelle ##-overskrifter: fremhæv selve nøgleordet.
   (list (concat "^#\\{1,6\\}[ \t]*"
                 "\\(Rum\\|Kort\\|Statblok\\|Brev\\|Monstre\\|Handling"
                 "\\|Fælder?\\|Gåde\\|NPC\\)[ \t]*:")
         '(1 'dnd-structural-face prepend)))
  "Ekstra font-lock-regler lagt oven på `markdown-mode'.")

;; ── Snippets (valgfrit — kun hvis yasnippet er til stede) ────────────────────

(defvar dnd-adventure--snippets-dir
  (expand-file-name
   "snippets"
   (file-name-directory (or load-file-name buffer-file-name default-directory)))
  "Mappe med de medfølgende yasnippet-snippets (`editor/snippets/').
Indeholder undermappen `dnd-adventure-mode/' (scene/rum/roster/statblok/ra/…).")

(with-eval-after-load 'yasnippet
  (when (file-directory-p dnd-adventure--snippets-dir)
    (add-to-list 'yas-snippet-dirs dnd-adventure--snippets-dir t)
    (yas-load-directory dnd-adventure--snippets-dir t)))

;; ── Keymap + mode ───────────────────────────────────────────────────────────

(defvar dnd-adventure-mode-map
  (let ((map (make-sparse-keymap)))
    (define-key map (kbd "C-c C-d m") #'dnd-insert-monster)
    (define-key map (kbd "C-c C-d r") #'dnd-refresh-data)
    (define-key map (kbd "C-c C-d .") #'dnd-goto-definition)
    (define-key map (kbd "C-c C-d b") #'dnd-browse)
    map)
  "Keymap for `dnd-adventure-mode'.")

;;;###autoload
(define-derived-mode dnd-adventure-mode markdown-mode "D&D-Adventure"
  "Major mode til at skrive D&D 3.5-eventyr (adventure.md).
Bygger på `markdown-mode' med @type[id]-completion, fremhævning og
indsæt-kommandoer mod srd35.db."
  (font-lock-add-keywords nil dnd-adventure--font-lock-keywords)
  (add-hook 'completion-at-point-functions
            #'dnd-adventure-completion-at-point nil t)
  (add-hook 'eldoc-documentation-functions #'dnd-adventure-eldoc nil t)
  (eldoc-mode 1)
  (add-hook 'flymake-diagnostic-functions #'dnd-adventure--flymake nil t)
  (flymake-mode 1)
  (when (fboundp 'yas-minor-mode) (yas-minor-mode 1)))

(provide 'dnd-adventure-mode)

;;; dnd-adventure-mode.el ends here
