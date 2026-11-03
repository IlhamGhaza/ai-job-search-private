% resume.cls - single-column, ATS-friendly CV class. Compile with lualatex or xelatex.
%
% The command names follow moderncv (\name, \address, \phone, \email, \extrainfo,
% \makecvtitle, \cventry), so a CV moves over by changing its preamble. It shares
% its font, colour and header with cover_letters/cover.cls.
%
% What keeps the text layer clean for an ATS:
% - One column and no tables, so extraction order is the visual order.
% - No icon fonts: every contact detail is printed as literal text.
% - Common ligatures off, so "fl" and "fi" stay separate letters.
% - No hyphenation, so a keyword is never split across two lines.
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{resume}[2026/10/31 ATS-friendly CV class]
\LoadClass[10pt,a4paper]{article}

\RequirePackage{iftex}
\ifpdftex
  \ClassError{resume}{resume.cls needs lualatex or xelatex}{It loads its fonts with fontspec, which pdflatex cannot run.}
\fi

\RequirePackage{fontspec}
\RequirePackage{xcolor}
\RequirePackage{enumitem}
\RequirePackage{needspace}
\RequirePackage[hidelinks]{hyperref}

% Fonts and colours: keep in step with cover.cls
\definecolor{accent}{HTML}{1F3A5F}
\definecolor{bodytext}{HTML}{222222}
\definecolor{muted}{HTML}{555555}
\definecolor{rulecolor}{HTML}{C5CDD8}

\setmainfont{Lato}[
  Path=../cover_letters/OpenFonts/fonts/lato/,
  Extension=.ttf,
  UprightFont=*-Reg,
  BoldFont=*-Bol,
  ItalicFont=*-RegIta,
  BoldItalicFont=*-BolIta,
  Ligatures={TeX,NoCommon},
]
\renewcommand{\normalsize}{\fontsize{10pt}{13.5pt}\selectfont}
\AtBeginDocument{\color{bodytext}\raggedright}
\hypersetup{colorlinks=true,linkcolor=accent,urlcolor=accent,pdfpagemode=UseNone}
\urlstyle{same}

\setlength{\parindent}{0pt}
\setlength{\parskip}{0pt}
\pagestyle{empty}
\hyphenpenalty=10000
\exhyphenpenalty=10000
\emergencystretch=2em

% Personal data
\def\@cvname{}\def\@cvaddress{}\def\@cvphone{}\def\@cvemail{}\def\@cvextra{}
\newcommand{\name}[2]{\def\@cvname{#1 #2}}
\newcommand{\address}[3]{\def\@cvaddress{#1}}
\newcommand{\phone}[2][mobile]{\def\@cvphone{#2}}
\newcommand{\email}[1]{\def\@cvemail{#1}}
\newcommand{\extrainfo}[1]{\def\@cvextra{#1}}

\newcommand{\contactsep}{\ \textcolor{rulecolor}{|}\ }
\newcommand{\makecvtitle}{%
  {\fontsize{22pt}{26pt}\selectfont\bfseries\color{accent}\@cvname\par}%
  \vspace{4pt}%
  {\color{muted}\fontsize{9.5pt}{13pt}\selectfont
    \@cvaddress\contactsep\href{mailto:\@cvemail}{\@cvemail}\contactsep\@cvphone
    \ifx\@cvextra\@empty\else\\\@cvextra\fi\par}%
  \vspace{6pt}%
  {\color{accent}\hrule height 1pt}%
  \vspace{8pt}%
}

% Section headings, kept as real sections in the text layer
\renewcommand{\section}[1]{%
  \par\addvspace{11pt}%
  \needspace{4\baselineskip}%
  {\fontsize{11pt}{14pt}\selectfont\bfseries\color{accent}#1\par}%
  \nopagebreak\vspace{2pt}%
  {\color{rulecolor}\hrule height 0.5pt}%
  \nopagebreak\vspace{5pt}%
}

% \cventry{dates}{title}{organisation}{location}{grade}{description}
% Plain paragraphs, so a long entry can break across pages. The first bullets
% stay with the header. Write dates with one ASCII hyphen: Jul 2025 - Feb 2026.
\newcommand{\cventry}[6]{%
  \par\addvspace{7pt}%
  \needspace{4\baselineskip}%
  {\bfseries #2}\hfill{\color{muted}#1}\par\nopagebreak
  {\color{muted}#3\if\relax\detokenize{#4}\relax\else, #4\fi\if\relax\detokenize{#5}\relax\else\contactsep #5\fi\par}%
  \nopagebreak\vspace{2pt}%
  #6\par
}

\setlist[itemize]{leftmargin=12pt,labelsep=5pt,topsep=1pt,partopsep=0pt,parsep=0pt,itemsep=1.5pt,label={\textbullet}}
