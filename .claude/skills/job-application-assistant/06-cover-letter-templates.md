---
framework_version: 1.0.2
---

# Cover Letter Templates and Tailoring Guide

## Template: `cover_letters/cover.cls` (XeLaTeX)

Cover letters use `cover.cls`, which shares its Lato font, navy accent and header with `cv/resume.cls`.

**Output file:** `cover_letters/cover_<company>_<role>.tex`
**Compile with:** XeLaTeX (cover.cls requires fontspec)
**Font directory:** `cover_letters/OpenFonts/fonts/`
**Candidate facts:** the master CV in `documents/cv/` (read-only, never overwritten) and `01-candidate-profile.md`

### Compile command

```bash
cd cover_letters && xelatex -interaction=nonstopmode cover_<company>_<role>.tex
```

Expected output: `Output written on cover_<company>_<role>.pdf (1 page)`. Any page count other than 1 is a failure that must be fixed before presenting to the user.

## Compile-and-Inspect Loop (MANDATORY)

After writing the cover letter and before presenting to the user, always compile and visually inspect the PDF. Iterate until the layout is clean:

1. Run `xelatex -interaction=nonstopmode cover_<company>_<role>.tex`
2. Confirm page count is exactly 1 and compile succeeded
3. Read the PDF via the Read tool and visually check: signature fits, no text cut off, links readable
4. Extract the text and count the body words, from the salutation to the closing: the target is 250-300

## Document Structure

```latex
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Cover Letter - [Company], [Role]
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\documentclass{cover}
\hypersetup{pdftitle={Muhammad Ilham Ghazali - Cover Letter},pdfauthor={Muhammad Ilham Ghazali}}
\begin{document}

\namesection{}{Muhammad Ilham Ghazali}{Bogor, West Java, Indonesia\contactsep \href{mailto:m.ilhamghazali@gmail.com}{m.ilhamghazali@gmail.com}\contactsep +62 813-1524-4423\\
\href{https://linkedin.com/in/muhammadilhamghazali}{linkedin.com/in/muhammadilhamghazali}\contactsep\href{https://github.com/IlhamGhaza}{github.com/IlhamGhaza}}

\currentdate{\today}

\lettercontent{Dear [Name/Team],}

\lettercontent{[Opening - the role, your strongest connection to it, why this company, 2-3 sentences]}

\lettercontent{[Evidence - the most relevant experience, leading into up to three bullets:]
\begin{itemize}
    \item \textbf{[Requirement]:} [what you did, with a real number where the profile has one]
    \item \textbf{[Requirement]:} [project or skill mapped to a posting requirement]
\end{itemize}}

\lettercontent{[Company - one verified specific about this company, and what you would contribute to it]}

\lettercontent{[Close - logistics the posting raises, and one plain sentence inviting the next step]}

\closing{Kind regards,}
\signature{Muhammad Ilham Ghazali}
\end{document}
```

## Key Commands Reference

| Command | Purpose |
|---------|---------|
| `\namesection{}{Name}{contact info}` | Header with name and contact |
| `\currentdate{date}` | Date field (use `\today` or explicit date) |
| `\lettercontent{text}` | Body paragraph (adds spacing after); may contain an `itemize` |
| `\contactsep` | Separator between contact details |
| `\closing{text}` | Closing line |
| `\signature{name}` | Printed name below signature |

## Tailoring Guidelines

### Salutation
- If you know the hiring manager's name: "Dear [First Last],"
- If you know the team: "Dear [Company] hiring team,"
- Generic: "Dear [Company]," (avoid "To whom it may concern")

### Length - Hard 1-Page Limit
- Target: 1 page including signature block
- Maximum: **never exceed 1 page**
- **Word budget: 250-300 words** of body text (not counting LaTeX markup).
- **Always count**: opening paragraph + bullet list paragraph + closing paragraph = 3 blocks. Add a 4th only if the others are short.
- When adding company-specific content, trim other content to compensate rather than adding net length

### Content and Voice
- **Company-specific motivation:** name at least one specific about the company, verified independently of the posting text. Never invent company information. If nothing can be verified, say why the role fits instead.
- **Relevance over coverage:** pick the two or three experiences closest to the posting and say what you would contribute with them. Do not retell the CV.
- **Natural language:** no stock phrases ("I am excited to apply", "passionate", "proven track record", "fast-paced environment", "leverage"), and no point made twice.
- **Honest gaps:** a stated requirement the candidate lacks gets one plain sentence and a bridge.

### Layout
- Do not change fonts, colours, margins or line spacing per application. If the letter overflows, cut words.
- Print contact details and link addresses as readable text. Text stays selectable and hyperlinks clickable because the class uses real fonts and `hyperref`.

### Bullet Lists
- Place `\begin{itemize}...\end{itemize}` inside `\lettercontent{}`, as in the template above. No font wrapper is needed
- Three bullets at most, and none if prose reads better
- Start each bullet with a bold label or action verb
- Use `\textbf{Label:}` for category-style bullets
- A bullet whose text begins with a literal `[` must be braced: `\item {[text]}`. Unbraced, LaTeX parses `[text]` as `\item`'s optional label and renders it off the left page edge, missing from the PDF text layer entirely

### LaTeX Special Characters
Escape these wherever they appear in body text:
- Ampersand: `\&` (company names: Brüel \& Kjær, H\&M) - unescaped, the compile fails loudly
- Percent: `\%` ("grew revenue 30\%") - unescaped, it does **not** fail: everything after the `%` on that line is silently eaten as a LaTeX comment
- Dollar: `\$`, hash: `\#`, underscore: `\_`
- Tilde: `\textasciitilde{}`, caret: `\textasciicircum{}`, backslash: `\textbackslash{}`

### Non-English Cover Letters
- Same template structure, just write content in the posting's language
- Adjust date format to local convention
- Adjust closing to local convention (e.g. "Med venlig hilsen," for Danish)

## Checklist Before Finalizing
- [ ] No em-dashes (use commas or periods instead)
- [ ] No cliches, empty filler or repeated points
- [ ] Body is 250-300 words
- [ ] Links are readable and clickable; text is selectable
- [ ] Every claim backed by specific example
- [ ] Forward-looking framing: focuses on tasks you'll solve, not just past duties
- [ ] Motivation section references a verified specific about this company
- [ ] Company name and role are correct throughout
- [ ] Date is current
- [ ] Fits on one page
- [ ] Language matches the job posting language
- [ ] Salutation is appropriate (named person if possible)
- [ ] Headline is engaging and specific, not generic

## Submission Guidelines (Best Practice)
- Submit only the documents the employer requests
- Export as PDF to preserve formatting
- Name files clearly: "[Your Name] CV" and "[Your Name] Cover Letter"
- Follow all employer instructions regarding anonymity or specific materials
