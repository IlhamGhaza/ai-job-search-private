import type { Site } from "./discovery.ts"

// Regional boards with no permitted job-seeker API. Every site is reached
// through the search provider only. `fetchable: true` means robots.txt allowed
// the posting path when checked (2026-10-30) and the site is not known to
// forbid automated reads; robots.txt is re-checked on every detail call. Big
// commercial boards whose terms restrict automated access stay discovery-only.
// Set a site's `fetchable` to false if you find its terms forbid it.
export const SITES: Site[] = [
  // Indonesia
  { key: "glints", name: "Glints", base: "https://glints.com", path: "/id/opportunities/jobs", country: "ID", fetchable: false, apply_method: "portal_login" },
  { key: "kalibrr", name: "Kalibrr", base: "https://www.kalibrr.com", path: "/c", country: "ID,PH", fetchable: true, apply_method: "portal_login" },
  { key: "dealls", name: "Dealls", base: "https://dealls.com", path: "", country: "ID", fetchable: true, apply_method: "portal_login" },
  { key: "kitalulus", name: "KitaLulus", base: "https://www.kitalulus.com", path: "", country: "ID", fetchable: true, apply_method: "portal_login" },
  { key: "karir", name: "Karir.com", base: "https://www.karir.com", path: "", country: "ID", fetchable: false, apply_method: "portal_login", note: "robots.txt disallows /jobs/" },
  { key: "techinasia", name: "Tech in Asia Jobs", base: "https://www.techinasia.com", path: "/jobs", country: "ID,SG,MY,PH,VN,TH", fetchable: true, apply_method: "portal_login" },
  // Malaysia, Thailand, Vietnam, Singapore
  { key: "hiredly", name: "Hiredly", base: "https://www.hiredly.com", path: "/jobs", country: "MY", fetchable: true, apply_method: "portal_login" },
  { key: "jobsdb-th", name: "JobsDB Thailand", base: "https://th.jobsdb.com", path: "/job", country: "TH", fetchable: false, apply_method: "portal_login", note: "SEEK group; robots.txt disallows */job/" },
  { key: "jobthai", name: "JobThai", base: "https://www.jobthai.com", path: "", country: "TH", fetchable: true, apply_method: "portal_login" },
  { key: "itviec", name: "ITviec", base: "https://itviec.com", path: "/it-jobs", country: "VN", fetchable: true, apply_method: "portal_login" },
  { key: "topdev", name: "TopDev", base: "https://topdev.vn", path: "", country: "VN", fetchable: true, apply_method: "portal_login" },
  { key: "vietnamworks", name: "VietnamWorks", base: "https://www.vietnamworks.com", path: "", country: "VN", fetchable: false, apply_method: "portal_login" },
  { key: "nodeflair", name: "NodeFlair", base: "https://nodeflair.com", path: "/jobs", country: "SG", fetchable: true, apply_method: "external_unknown" },
  // Japan, Korea
  { key: "tokyodev", name: "TokyoDev", base: "https://www.tokyodev.com", path: "/companies", country: "JP", fetchable: true, apply_method: "external_unknown" },
  { key: "japandev", name: "Japan Dev", base: "https://japan-dev.com", path: "/jobs", country: "JP", fetchable: true, apply_method: "external_unknown" },
  { key: "gaijinpot", name: "GaijinPot Jobs", base: "https://jobs.gaijinpot.com", path: "", country: "JP", fetchable: true, apply_method: "portal_login" },
  { key: "wanted", name: "Wanted", base: "https://www.wanted.co.kr", path: "/wd", country: "KR", fetchable: false, apply_method: "portal_login" },
  { key: "saramin", name: "Saramin", base: "https://www.saramin.co.kr", path: "", country: "KR", fetchable: false, apply_method: "portal_login", note: "official API needs an approved key; not wired" },
  { key: "jumpit", name: "Jumpit", base: "https://www.jumpit.co.kr", path: "/position", country: "KR", fetchable: false, apply_method: "portal_login" },
  // Australia, New Zealand
  { key: "seek-au", name: "SEEK Australia", base: "https://www.seek.com.au", path: "/job", country: "AU", fetchable: false, apply_method: "portal_login" },
  { key: "seek-nz", name: "SEEK New Zealand", base: "https://www.seek.co.nz", path: "/job", country: "NZ", fetchable: false, apply_method: "portal_login" },
  { key: "jora", name: "Jora Australia", base: "https://au.jora.com", path: "/job", country: "AU", fetchable: false, apply_method: "external_unknown", note: "robots.txt disallows everything" },
  { key: "trademe", name: "Trade Me Jobs", base: "https://www.trademe.co.nz", path: "/a/jobs", country: "NZ", fetchable: false, apply_method: "portal_login" },
  // UK, Ireland
  { key: "wttj", name: "Welcome to the Jungle (Otta)", base: "https://www.welcometothejungle.com", path: "/en/companies", country: "GB", fetchable: false, apply_method: "portal_login" },
  { key: "reed", name: "Reed", base: "https://www.reed.co.uk", path: "/jobs", country: "GB", fetchable: false, apply_method: "portal_login" },
  { key: "cwjobs", name: "CWJobs", base: "https://www.cwjobs.co.uk", path: "/job", country: "GB", fetchable: false, apply_method: "portal_login" },
  { key: "irishjobs", name: "IrishJobs", base: "https://www.irishjobs.ie", path: "/job", country: "IE", fetchable: false, apply_method: "portal_login" },
  // Germany, Austria, Switzerland
  { key: "stepstone", name: "StepStone", base: "https://www.stepstone.de", path: "/stellenangebote", country: "DE", fetchable: false, apply_method: "portal_login" },
  { key: "berlinstartupjobs", name: "Berlin Startup Jobs", base: "https://berlinstartupjobs.com", path: "", country: "DE", fetchable: true, apply_method: "external_unknown" },
  { key: "germantechjobs", name: "GermanTechJobs", base: "https://germantechjobs.de", path: "/jobs", country: "DE", fetchable: true, apply_method: "external_unknown" },
  { key: "karriere", name: "karriere.at", base: "https://www.karriere.at", path: "/jobs", country: "AT", fetchable: true, apply_method: "portal_login" },
  { key: "jobsch", name: "jobs.ch", base: "https://www.jobs.ch", path: "/en/vacancies", country: "CH", fetchable: false, apply_method: "portal_login", note: "robots.txt disallows vacancy detail pages" },
  { key: "swissdevjobs", name: "SwissDevJobs", base: "https://swissdevjobs.ch", path: "/jobs", country: "CH", fetchable: true, apply_method: "external_unknown" },
  // Netherlands, Belgium, Luxembourg
  { key: "werk", name: "Werk.nl", base: "https://www.werk.nl", path: "/vacatures", country: "NL", fetchable: true, apply_method: "external_unknown" },
  { key: "vdab", name: "VDAB", base: "https://www.vdab.be", path: "/vindeenjob/vacatures", country: "BE", fetchable: true, apply_method: "external_unknown" },
  { key: "moovijob", name: "Moovijob", base: "https://www.moovijob.com", path: "", country: "LU", fetchable: true, apply_method: "external_unknown" },
  // Nordics (Jobindex/Jobnet already have their own CLIs)
  { key: "thehub", name: "The Hub", base: "https://thehub.io", path: "/jobs", country: "DK,SE,NO,FI", fetchable: true, apply_method: "external_unknown" },
  { key: "duunitori", name: "Duunitori", base: "https://duunitori.fi", path: "/tyopaikat", country: "FI", fetchable: true, apply_method: "external_unknown" },
  { key: "finn", name: "FINN jobb", base: "https://www.finn.no", path: "/job", country: "NO", fetchable: false, apply_method: "portal_login" },
  { key: "alfred", name: "Alfred", base: "https://alfred.is", path: "", country: "IS", fetchable: true, apply_method: "portal_login" },
  // Global remote boards with no public API or feed (checked 2026-10-30).
  // "GLOBAL,REMOTE" selects them with --country GLOBAL and leaves `country` null on leads.
  { key: "justremote", name: "JustRemote", base: "https://justremote.co", path: "/remote-jobs", country: "GLOBAL,REMOTE", fetchable: true, apply_method: "external_unknown" },
  { key: "remotelyjobs", name: "Remotely.jobs", base: "https://www.remotely.jobs", path: "", country: "GLOBAL,REMOTE", fetchable: true, apply_method: "external_unknown", note: "robots.txt disallows /j/, /apply/ and /search; detail re-checks per URL" },
  { key: "powertofly", name: "PowerToFly", base: "https://powertofly.com", path: "/jobs", country: "GLOBAL,REMOTE", fetchable: true, apply_method: "portal_login", note: "robots.txt disallows /api/*" },
  { key: "jobhunt", name: "Job-Hunt.org", base: "https://www.job-hunt.org", path: "", country: "GLOBAL,REMOTE", fetchable: true, apply_method: "external_unknown", note: "mostly career advice; robots.txt disallows query URLs" },
  // United States, Canada
  { key: "wellfound", name: "Wellfound", base: "https://wellfound.com", path: "/jobs", country: "US", fetchable: false, apply_method: "portal_login" },
  { key: "builtin", name: "Built In", base: "https://builtin.com", path: "/job", country: "US", fetchable: false, apply_method: "external_unknown" },
  { key: "dice", name: "Dice", base: "https://www.dice.com", path: "/job-detail", country: "US", fetchable: false, apply_method: "portal_login", note: "robots.txt disallows /job" },
  { key: "indeed", name: "Indeed", base: "https://www.indeed.com", path: "/viewjob", country: "US", fetchable: false, apply_method: "portal_login" },
  { key: "jobbank-ca", name: "Job Bank Canada", base: "https://www.jobbank.gc.ca", path: "/jobsearch/jobposting", country: "CA", fetchable: true, apply_method: "external_unknown" },
]
