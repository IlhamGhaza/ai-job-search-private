% cover.cls - one-page cover letter class. Compile with xelatex.
%
% Shares its font, colour and header with cv/resume.cls. \lettercontent can hold
% an itemize directly and every paragraph uses one font, so no \fontspec wrapper
% is needed around a list. Common ligatures and hyphenation are off to keep the
% text layer clean.
\ProvidesClass{cover}[2026/10/31 Cover letter class]
\NeedsTeXFormat{LaTeX2e}
\DeclareOption*{%
  \PassOptionsToClass{\CurrentOption}{article}
}
\ProcessOptions\relax
\LoadClass[a4paper]{article}

% Package Imports
\usepackage[hmargin=25mm,top=22mm,bottom=22mm]{geometry}
\usepackage{xcolor}
\usepackage{fontspec}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}

% Fonts and colours: keep in step with resume.cls
\definecolor{accent}{HTML}{1F3A5F}
\definecolor{bodytext}{HTML}{222222}
\definecolor{muted}{HTML}{555555}
\definecolor{rulecolor}{HTML}{C5CDD8}

\setmainfont{Lato}[
  Path=OpenFonts/fonts/lato/,
  Extension=.ttf,
  UprightFont=*-Reg,
  BoldFont=*-Bol,
  ItalicFont=*-RegIta,
  BoldItalicFont=*-BolIta,
  Ligatures={TeX,NoCommon},
]
\renewcommand{\normalsize}{\fontsize{10.5pt}{15pt}\selectfont}
\AtBeginDocument{\color{bodytext}\raggedright}
\hypersetup{colorlinks=true,linkcolor=accent,urlcolor=accent,pdfpagemode=UseNone}
\urlstyle{same}

\setlength{\parindent}{0pt}
\setlength{\parskip}{0pt}
\pagestyle{empty}
\hyphenpenalty=10000
\exhyphenpenalty=10000
\emergencystretch=2em

\newcommand{\contactsep}{\ \textcolor{rulecolor}{|}\ }

% \namesection{unused}{name}{contact line}
\newcommand{\namesection}[3]{%
  {\fontsize{22pt}{26pt}\selectfont\bfseries\color{accent}#1#2\par}%
  \vspace{4pt}%
  {\color{muted}\fontsize{9.5pt}{13pt}\selectfont #3\par}%
  \vspace{6pt}%
  {\color{accent}\hrule height 1pt}%
  \vspace{14pt}%
}

% Letter blocks. A recipient block is optional.
\newcommand{\currentdate}[1]{{\color{muted}#1\par}\vspace{10pt}}
\newcommand{\companyname}[1]{{\bfseries #1\par}}
\newcommand{\companyaddress}[1]{{#1\par}\vspace{10pt}}
\newcommand{\lettercontent}[1]{{#1\par}\vspace{9pt}}
\newcommand{\closing}[1]{\vspace{3pt}{#1\par}\vspace{16pt}}
\newcommand{\signature}[1]{{\bfseries #1\par}}

\setlist[itemize]{leftmargin=14pt,labelsep=5pt,topsep=3pt,partopsep=0pt,parsep=0pt,itemsep=3pt,label={\textbullet}}
