;;; dnd-browse.el --- Read-only browser over srd35.db -*- lexical-binding: t; -*-

;; Author: flask-dnd-3.5
;; Version: 1
;; Package-Requires: ((emacs "29.1"))
;; Keywords: games

;;; Commentary:

;; En browsbar oversigt over hele referencebanken i `srd35.db' (monstre, dyr,
;; fælder, spells, feats, items, våben, skills, tilstande, domæner), så
;; forfatteren kan se "hvad findes der overhovedet" mens hun skriver et eventyr.
;;
;; Ånd som resten af `dnd-adventure-mode': INGEN build, INGEN kørende server,
;; indbygget SQLite (Emacs 29+), altid READ-ONLY mod db'en (kun SELECT/PRAGMA).
;;
;;   * M-x dnd-browse — vælg en tabel → sorterbar liste (`tabulated-list-mode').
;;   * RET  → detalje-visning: ALLE felter for rækken (hele spell-teksten,
;;            statblokken, feat-benefit osv.) i en read-only buffer.
;;   * i    → indsæt @monster[id]/@faelde[id] i det adventure-buffer browseren
;;            blev åbnet fra (kun for referérbare tabeller; ellers klar besked).
;;   * s    → sortér på kolonnen ved punktet.
;;   * /    → filtrér på navn (regexp; tomt = ryd).
;;   * g    → genindlæs rækker (indbygget i `tabulated-list-mode').
;;
;; Hvilke tabeller der browses — og med hvilke kolonner — er ren DATA i
;; `dnd-browse--tables'; en ny tabel er en alist-post, ikke kode.
;;
;; Genbruger `dnd-adventure--db-path' fra `dnd-adventure-mode' til at lokalisere
;; db'en (op fra den åbne fil til repo-roden).

;;; Code:

(require 'dnd-adventure-mode)           ; db-path-helper + samme db-lokalisering
(require 'tabulated-list)
(require 'cl-lib)                        ; cl-loop i detalje-visningen
(require 'seq)                           ; seq-filter i filtreringen

;; ── Tabel-spec (data — nye tabeller er poster her, ikke kode) ────────────────

(defconst dnd-browse--tables
  '((monsters
     :label "Monstre" :ref "monster"
     :columns (("Navn" name 26) ("CR" cr 5) ("HP" hp_max 5) ("AC" ac 4) ("Type" type 16))
     :sort "name")
    (animals
     :label "Dyr" :ref "monster"
     :columns (("Navn" name 26) ("Str." size 8) ("Type" type 16) ("HD" base_hd 4))
     :sort "name")
    (traps
     :label "Fælder" :ref "faelde"
     :columns (("Navn" name 26) ("CR" cr 5) ("Type" trap_type 16) ("Trigger" trigger 12))
     :sort "name")
    (spells
     :label "Spells" :ref nil
     :columns (("Navn" name 30) ("Skole" school 16) ("Wiz" level_wizard 4) ("Clr" level_cleric 4))
     :sort "name")
    (feats     :label "Feats"      :ref nil :columns (("Navn" name 30) ("Type" type 16)) :sort "name")
    (items     :label "Items"      :ref nil :columns (("Navn" name 30) ("Kategori" category 16) ("Vægt" weight 6)) :sort "name")
    (weapons   :label "Våben"      :ref nil :columns (("Navn" name 26) ("Klasse" weapon_class 12) ("Skade (M)" dmg_m 10)) :sort "name")
    (skills    :label "Skills"     :ref nil :columns (("Navn" name 26) ("Evne" ability 6)) :sort "name")
    (conditions :label "Tilstande" :ref nil :columns (("Navn" name 26)) :sort "name")
    (domains   :label "Domæner"    :ref nil :columns (("Navn" name 26)) :sort "name"))
  "Browsbare srd35.db-tabeller.
Hver post: (TABEL :label STR :ref TYPE-eller-nil
            :columns ((HEADER SQL-KOLONNE BREDDE)…) :sort SQL-KOLONNE).
`id' hentes altid som skjult nøgle uanset `:columns', så rækkens id
kendes af RET/i.  `:ref' ≠ nil = tabellen kan indsættes som @TYPE[id]
(kun monster/fælde resolver som ref i appen).")

;; ── Buffer-lokal tilstand ────────────────────────────────────────────────────

(defvar-local dnd-browse--table nil
  "Tabel-nøgle (symbol) for denne browse-buffer.")
(defvar-local dnd-browse--path nil
  "srd35.db-sti denne browse-buffer læser fra (låst ved åbning).")
(defvar-local dnd-browse--origin nil
  "Adventure-bufferen `dnd-browse-insert-ref' indsætter @TYPE[id] i.")
(defvar-local dnd-browse--filter nil
  "Aktivt navn-filter (regexp) eller nil.")

(defun dnd-browse--spec (key)
  "Slå tabel-spec op for KEY (symbol)."
  (or (assq key dnd-browse--tables)
      (error "Ukendt browse-tabel: %s" key)))

;; ── Read-only db-adgang (klar fejl, i modsætning til mode-filens bløde query) ─

(defun dnd-browse--select (path sql &rest params)
  "Kør SELECT/PRAGMA SQL med PARAMS mod srd35.db på PATH; returnér rækkerne.
Signalér en klar `user-error' hvis SQLite eller db'en mangler (browseren
skal fejle tydeligt, ikke tomt)."
  (unless (and (fboundp 'sqlite-available-p) (sqlite-available-p))
    (user-error "Denne Emacs har ikke indbygget SQLite (kræver Emacs 29+)"))
  (unless (file-exists-p path)
    (user-error "srd35.db ikke fundet: %s — kør `python importer.py'" path))
  (let ((db (sqlite-open path)))
    (unwind-protect
        (sqlite-select db sql params)
      (sqlite-close db))))

(defun dnd-browse--cell (value)
  "Formatér en db-VALUE som celle-streng (nil → tom streng)."
  (if value (format "%s" value) ""))

;; ── Rækker → tabulated-list-entries ─────────────────────────────────────────

(defun dnd-browse--rows (path spec)
  "Byg `tabulated-list-entries'-liste for SPEC fra db'en på PATH.
Hver post: (ID [celle …]) med ID som skjult entry-nøgle."
  (let* ((table (symbol-name (car spec)))
         (cols (plist-get (cdr spec) :columns))
         (sort (plist-get (cdr spec) :sort))
         (sqlcols (mapcar (lambda (c) (symbol-name (nth 1 c))) cols))
         (sql (format "SELECT id, %s FROM %s ORDER BY %s"
                      (mapconcat #'identity sqlcols ", ") table sort))
         (rows (dnd-browse--select path sql)))
    (mapcar (lambda (row)
              (list (dnd-browse--cell (car row))
                    (vconcat (mapcar #'dnd-browse--cell (cdr row)))))
            rows)))

(defun dnd-browse--entries ()
  "`tabulated-list-entries'-funktion: rækker for denne buffers tabel.
Filtreres på navn (første kolonne) hvis `dnd-browse--filter' er sat."
  (let ((entries (dnd-browse--rows dnd-browse--path
                                   (dnd-browse--spec dnd-browse--table))))
    (if dnd-browse--filter
        (let ((case-fold-search t))
          (seq-filter (lambda (e)
                        (string-match-p dnd-browse--filter (aref (nth 1 e) 0)))
                      entries))
      entries)))

;; ── Detalje-visning (RET) ────────────────────────────────────────────────────

(defun dnd-browse--field-names (path table)
  "Kolonnenavne for TABLE i deklareret rækkefølge (via PRAGMA table_info)."
  (mapcar (lambda (r) (nth 1 r))
          (dnd-browse--select path (format "PRAGMA table_info(%s)" table))))

(defun dnd-browse-show-detail ()
  "Vis ALLE felter for rækken ved punktet i en read-only buffer."
  (interactive)
  (let ((id (tabulated-list-get-id)))
    (unless id (user-error "Ingen række ved punktet"))
    (let* ((path dnd-browse--path)
           (spec (dnd-browse--spec dnd-browse--table))
           (table (symbol-name (car spec)))
           (label (plist-get (cdr spec) :label))
           (fields (dnd-browse--field-names path table))
           (collist (mapconcat #'identity fields ", "))
           (row (car (dnd-browse--select
                      path (format "SELECT %s FROM %s WHERE id = ?" collist table)
                      id)))
           (buf (get-buffer-create (format "*dnd-detalje: %s [%s]*" label id))))
      (unless row (user-error "Rækken %s findes ikke længere" id))
      (with-current-buffer buf
        (let ((inhibit-read-only t))
          (erase-buffer)
          (cl-loop
           for name in fields
           for value in row
           do (let ((v (dnd-browse--cell value)))
                (if (string-match-p "\n" v)
                    (insert (propertize (format "%s:\n" name) 'face 'bold) v "\n\n")
                  (insert (propertize (format "%-18s" (concat name ":")) 'face 'bold)
                          v "\n"))))
          (goto-char (point-min)))
        (special-mode))
      (pop-to-buffer buf))))

;; ── Indsæt @TYPE[id] i oprindelses-bufferen (i) ─────────────────────────────

(defun dnd-browse-insert-ref ()
  "Indsæt @TYPE[id] for rækken ved punktet i adventure-bufferen.
Kun for referérbare tabeller (`:ref' ≠ nil); ellers en klar besked."
  (interactive)
  (let* ((spec (dnd-browse--spec dnd-browse--table))
         (ref (plist-get (cdr spec) :ref))
         (label (plist-get (cdr spec) :label))
         (id (tabulated-list-get-id)))
    (unless id (user-error "Ingen række ved punktet"))
    (unless ref
      (user-error "%s kan ikke refereres — kun monstre og fælder resolver som @type[id]"
                  label))
    (unless (buffer-live-p dnd-browse--origin)
      (user-error "Intet adventure-buffer at indsætte i (browseren blev ikke åbnet fra et)"))
    (let ((text (format "@%s[%s]" ref id)))
      (with-current-buffer dnd-browse--origin
        (insert text))
      (message "Indsatte %s i %s" text (buffer-name dnd-browse--origin)))))

;; ── Filtrering (/) ───────────────────────────────────────────────────────────

(defun dnd-browse-filter (regexp)
  "Filtrér listen på navn med REGEXP (tomt = ryd filteret)."
  (interactive (list (read-string "Filtrér navn (regexp, tomt = ryd): ")))
  (setq dnd-browse--filter (and (not (string-empty-p regexp)) regexp))
  (tabulated-list-revert)
  (message (if dnd-browse--filter "Filter: %s" "Filter ryddet")
           dnd-browse--filter))

;; ── Mode + kommando ──────────────────────────────────────────────────────────

(defvar dnd-browse-mode-map
  (let ((map (make-sparse-keymap)))
    (define-key map (kbd "RET") #'dnd-browse-show-detail)
    (define-key map (kbd "i")   #'dnd-browse-insert-ref)
    (define-key map (kbd "s")   #'tabulated-list-sort)
    (define-key map (kbd "/")   #'dnd-browse-filter)
    map)
  "Keymap for `dnd-browse-mode' (arver `tabulated-list-mode-map': g/n/p…).")

(define-derived-mode dnd-browse-mode tabulated-list-mode "D&D-Browse"
  "Read-only browser over en srd35.db-tabel."
  (setq tabulated-list-padding 1))

(defun dnd-browse--setup ()
  "Sæt format/entries fra denne buffers tabel-spec og print listen."
  (let* ((spec (dnd-browse--spec dnd-browse--table))
         (cols (plist-get (cdr spec) :columns)))
    (setq tabulated-list-format
          (vconcat (mapcar (lambda (c) (list (nth 0 c) (nth 2 c) t)) cols)))
    (setq tabulated-list-sort-key (cons (nth 0 (car cols)) nil))
    (setq tabulated-list-entries #'dnd-browse--entries)
    (tabulated-list-init-header)
    (tabulated-list-print)))

;;;###autoload
(defun dnd-browse ()
  "Browse referencebanken i srd35.db: vælg en tabel → sorterbar liste.
Åbnes fra et adventure-buffer, så `i' kan indsætte @type[id] tilbage i det."
  (interactive)
  (let* ((labels (mapcar (lambda (s) (cons (plist-get (cdr s) :label) (car s)))
                         dnd-browse--tables))
         (pick (completing-read "Referencebank: " labels nil t))
         (key (cdr (assoc pick labels)))
         (path (dnd-adventure--db-path))
         (origin (current-buffer))
         (buf (get-buffer-create (format "*dnd-browse: %s*" pick))))
    (with-current-buffer buf
      (dnd-browse-mode)
      (setq dnd-browse--table key
            dnd-browse--path path
            dnd-browse--origin origin
            dnd-browse--filter nil)
      (dnd-browse--setup))
    (pop-to-buffer buf)))

(provide 'dnd-browse)

;;; dnd-browse.el ends here
