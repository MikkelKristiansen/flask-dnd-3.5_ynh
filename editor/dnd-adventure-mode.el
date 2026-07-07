;;; dnd-adventure-mode.el --- Skrivestøtte til D&D 3.5-eventyr (adventure.md) -*- lexical-binding: t; -*-

;; Author: flask-dnd-3.5
;; Version: 1 (v1: font-lock + monster-completion + indsæt-kommando)
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
;;
;; v2 (npc/kort/brev-completion fra bufferen, eldoc-preview, xref, lint) er
;; beskrevet i briefs/BRIEF-emacs-dnd-mode-v2.md.

;;; Code:

(require 'markdown-mode)

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

;;;###autoload
(defun dnd-refresh-data ()
  "Glem cachet SRD-data (efter en `python importer.py')."
  (interactive)
  (setq dnd-adventure--monster-cache nil)
  (message "D&D-data genindlæses ved næste opslag."))

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

(defun dnd-adventure--candidates (type)
  "Completion-kandidater for entity-TYPE.  v1 kender kun \"monster\" (fra db).
v2 udvider med dokument-lokale typer (npc/kort/brev) parset fra bufferen."
  (when (string= type "monster")
    (mapcar #'car (dnd-adventure--monsters))))

(defun dnd-adventure-completion-at-point ()
  "`completion-at-point-functions'-indgang for @type[id]-referencer."
  (let ((ctx (dnd-adventure--entity-context)))
    (when ctx
      (let* ((type (nth 0 ctx))
             (start (nth 1 ctx))
             (end (nth 2 ctx))
             (cands (dnd-adventure--candidates type)))
        (when cands
          (list start end cands
                :exclusive 'no
                :annotation-function #'dnd-adventure--annotate))))))

(defun dnd-adventure--annotate (id)
  "Vis monsterets navn som annotation ved siden af ID i completion-listen."
  (let ((name (cdr (assoc id dnd-adventure--monster-cache))))
    (and name (concat "  " name))))

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

;; ── Keymap + mode ───────────────────────────────────────────────────────────

(defvar dnd-adventure-mode-map
  (let ((map (make-sparse-keymap)))
    (define-key map (kbd "C-c C-d m") #'dnd-insert-monster)
    (define-key map (kbd "C-c C-d r") #'dnd-refresh-data)
    map)
  "Keymap for `dnd-adventure-mode'.")

;;;###autoload
(define-derived-mode dnd-adventure-mode markdown-mode "D&D-Adventure"
  "Major mode til at skrive D&D 3.5-eventyr (adventure.md).
Bygger på `markdown-mode' med @type[id]-completion, fremhævning og
indsæt-kommandoer mod srd35.db."
  (font-lock-add-keywords nil dnd-adventure--font-lock-keywords)
  (add-hook 'completion-at-point-functions
            #'dnd-adventure-completion-at-point nil t))

(provide 'dnd-adventure-mode)

;;; dnd-adventure-mode.el ends here
