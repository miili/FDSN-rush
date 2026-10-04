# Reference specs

FDSN web service specifications used as background for `client.py` and `models/`.
The PDFs and converted text are not committed. Fetch them with:

```sh
cd reference && just        # download + convert (needs just, curl, pdftotext)
```

Result: `fdsnws-station-1.1.{pdf,txt}` and `fdsnws-dataselect-1.1.{pdf,txt}`.
The spec summary is in `NOTES.md`. Errata and code-vs-spec differences are in `AGENTS.md` ("FDSN protocol notes").
