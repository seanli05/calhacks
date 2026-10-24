"""One module per writer (rule 5). A component imports only its own writer module,
plus `app.db.reads`, `app.db.events`, `app.db.messages`, and `app.db.jobs`."""
