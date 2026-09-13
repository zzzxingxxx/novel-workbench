# ADR-003: Operations and revisions

AI and user content changes are represented by an operation. Creating an operation stores a pending preview. Approval applies it in one transaction and creates a revision; rejection leaves content unchanged. The target `old_hash` is checked when the preview is created and again when it is approved so a newer edit cannot be overwritten.
