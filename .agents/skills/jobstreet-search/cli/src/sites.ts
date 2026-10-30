import type { Site } from "./discovery.ts"

// JobStreet (SEEK Asia). SEEK's APIs serve hirers, not job seekers, and every
// JobStreet robots.txt disallows */job/ for generic clients: postings are
// discovered through the search provider only and never fetched.
export const SITES: Site[] = [
  { key: "id", name: "JobStreet Indonesia", base: "https://id.jobstreet.com", path: "/job", country: "ID", fetchable: false, apply_method: "portal_login" },
  { key: "my", name: "JobStreet Malaysia", base: "https://my.jobstreet.com", path: "/job", country: "MY", fetchable: false, apply_method: "portal_login" },
  { key: "ph", name: "JobStreet Philippines", base: "https://ph.jobstreet.com", path: "/job", country: "PH", fetchable: false, apply_method: "portal_login" },
  { key: "sg", name: "JobStreet Singapore", base: "https://sg.jobstreet.com", path: "/job", country: "SG", fetchable: false, apply_method: "portal_login" },
]
