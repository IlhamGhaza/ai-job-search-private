---
framework_version: 1.1.2
---

# Candidate Profile

<!-- SETUP: This file is populated by running /setup -->
<!-- After running /setup, all sections will be filled with your actual information -->

## Identity
- **Name:** Muhammad Ilham Ghazali
- **Location:** Bogor, West Java, Indonesia
- **Phone:** +62 813-1524-4423
- **Email:** m.ilhamghazali@gmail.com
- **LinkedIn:** https://linkedin.com/in/muhammadilhamghazali
- **GitHub:** https://github.com/IlhamGhaza
- **Portfolio/Demos:** https://ilhamghaza.github.io
- **Status:** Available immediately
- **Constraints:** Remote-first, but onsite work is acceptable (candidate-confirmed 2026-10-30); open to relocation in the `relocation_countries` of `tools/data/salary_benchmarks.json` (the 20 developed markets plus Malaysia, Philippines, Thailand, Vietnam, Brunei and Timor-Leste). Full-time, contract or freelance; internships only when paid and, by default, remote (`--intern`, see 04-job-evaluation.md).

### Languages
<!-- Every language you can work in professionally, with your honest level. Used by the
Language Gate in 04-job-evaluation.md and by job-scraper/search-queries.md's query-language
generation. Omit any language you don't actually work in - an undeclared language is treated as
a hard no, not a gap to smooth over. -->

| Language | Level | Notes |
|----------|-------|-------|
| Indonesian | Native | |
| English | Intermediate | |

## Job Search Target (global junior Flutter search)
<!-- Preferences and deal-breakers for /scrape and /rank. The binding rules are in
04-job-evaluation.md ("Global Junior Flutter Search - Hard Rules") and tools/job_rules.py. -->
- **Primary target:** Junior / Entry-level Flutter Developer or Engineer. Also Junior Dart, Junior Mobile, Junior Cross-Platform, Associate / Graduate Mobile Engineer - only when it is a real full-time job. Judged by real duties and required experience, not title.
- **Accept:** full-time, a paid contract/freelance engagement, or a paid internship the `--intern` mode allows (default `remote`). **Reject:** unpaid roles in every mode, student-only placements, internships outside the mode, bootcamps / training programs, senior or lead roles.
- **Geography:** global search. Priority countries (ranking only, not a filter) are the relocation countries plus Indonesia, from the same config list. Indonesian citizen, willing to relocate.
- **Never assumed:** that an international remote job accepts Indonesia-based applicants, or that an employer sponsors a visa or relocation, without explicit evidence.
- **Hard rules:** Cambodia-based jobs always rejected; India onsite/hybrid always rejected (India remote only if it clears the salary floor); a remote job must pay strictly more than the configured salary floor (currently IDR 5,729,876/month, UMP DKI Jakarta 2026) after conversion, and an onsite or hybrid job's estimated net pay must exceed the higher of that floor and the local living cost; undisclosed pay is estimated from the salary tier (A/B processed, C rejected); a remote internship needs stated pay above zero, and India remote internships keep the floor; safety screening is a separate stage and nothing unverified outranks a verified job.

## Education

| Degree | Period | Institution | Key Topics |
|--------|--------|-------------|------------|
| Bachelor of Information Systems (graduated 2026; confirmed by candidate 2026-10-30) | Sep 2022 - Aug 2026 | Universitas Gunadarma | GPA 3.72; Member, Google Developer Group on Campus (GDGOC) |

## Professional Experience

### Mobile Developer (Contract) - Quetra Asia Klandesin (Jul 2025 - Feb 2026)
Serpong, Indonesia
- Delivered five Flutter client apps across HRIS, fleet management, POS, inventory management, and IoT workflows, covering member/admin roles, GPS tracking, and device control over MQTT
- Built photo-based attendance with location capture and office-radius restriction for the HRIS apps
- Implemented GPS tracking and driver job workflow states (view, accept, reject, pause, complete) for fleet management
- Integrated the app with devices over MQTT to display device status and manage time-based schedules for the IoT watering app
- Implemented JWT authentication with token refresh, expired-session handling, and secure token storage in flutter_secure_storage
- Structured apps in core, data, and presentation layers with BLoC and GetX
- Worked with a backend developer on API contracts, joined client requirement discussions, estimates, and UAT on several projects, and handled client change requests after delivery

### Mobile Developer Intern - Pansus Studio (Aug 2025 - Mar 2026)
Bandung, Indonesia
- Built features for a multi-role food ordering app for User, Merchant, and Driver roles within a 3-developer Flutter team
- Converted Figma designs into responsive screens and integrated REST APIs for authentication and order management
- Used BLoC and Clean Architecture in an Agile monorepo, tested features, and fixed bugs before deployment

### Mobile Developer Intern - Kita Bantu Indonesia (Mar 2025 - Jun 2025)
Jakarta, Indonesia
- Coordinated a 4-person mobile team on a job portal app, distributed tasks, synced with other teams, and delivered a working MVP in 8 weeks without a project manager
- Converted 20+ Figma screens into responsive mobile interfaces and worked with 2 designers and 3 backend developers to resolve integration issues

### Laboratory Assistant and Tutor - Information Systems Laboratory, Universitas Gunadarma (Oct 2023 - Jan 2025)
Depok, Indonesia
- Taught C programming labs, supported 30+ students with debugging, and produced slides and code examples reused by other tutors

## Independent Projects
<!-- Projects outside of employment: freelance, open source, personal -->
- **Point of Sale (POS) App**: Cross-platform POS built with Flutter, BLoC, SQLite, Laravel REST API, and Midtrans payments; invoice generation with SQLite caching, low-stock alerts, draft orders, and financial reports with charts
- **Online Attendance App with Face Detection**: Flutter, BLoC, SQLite, Laravel, TensorFlow Lite, Google Maps, FCM; face detection, geofencing, FCM reminders, daily/monthly reports, offline caching that syncs when online
- **Flutter Movie App** (Dicoding Expert course project): Flutter, BLoC, Dio, Codemagic; movie app with BLoC state management, Dio REST API calls, unit/widget tests, SSL pinning, Codemagic CI/CD pipeline
- **Food Recognition App** (Dicoding ML for Flutter course project): Flutter, Provider, Google Gemini API, TheMealDB API; identifies food from camera/gallery photos via Gemini API and fetches recipes from TheMealDB; handles permissions with permission_handler and manages API keys via envied

## Technical Skills

### Programming & ML
- **Dart/Flutter** (primary): BLoC, GetX, Provider, Clean Architecture
- **Riverpod and GoRouter:** hands-on experience, stated by the candidate 2026-10-30 (project or employer context not specified, so tie no bullet to a named role)
- **Kotlin:** learned, no professional experience (candidate-stated 2026-10-30); do not present as work experience
- **Backend fundamentals (Redis and related):** self-study, no professional experience (candidate-stated 2026-10-30); specific frameworks/projects not stated, so name none and never present as work experience
- **Other languages:** SQL, basic Laravel (PHP), Node.js
- **ML/AI:** TensorFlow Lite, Google Gemini API (on-device/API-based inference, not model training)

### Domain Expertise
- Mobile app development: HRIS, fleet management, POS, inventory management, food ordering, IoT control apps
- REST API integration (Dio), JWT authentication with token refresh, secure token storage (flutter_secure_storage)
- Firebase (Auth, FCM, data storage), MQTT device integration, Google Maps, Midtrans payments

### Software & Tools
- Git, GitHub, Codemagic CI/CD, unit/widget testing, SSL pinning
- Figma (design-to-code conversion), SQLite

## Publications
<!-- List peer-reviewed publications, if any -->
None.

## Awards
None listed.

## Certifications
- Menjadi Flutter Developer Expert (Dicoding, Credential ID ERZREQDOQXYV) - Jun 2025
- Belajar Pengembangan Aplikasi Flutter Intermediate (Dicoding, Credential ID L4PQENK6OPO1) - Jun 2025
- Belajar Penerapan Machine Learning untuk Flutter (Dicoding, Credential ID N9ZO9WWJ6XG5) - Jun 2025
- Belajar Fundamental Aplikasi Flutter (Dicoding, Credential ID MRZMN0W2RPYQ) - Jun 2025
- Memulai Pemrograman dengan Dart (Dicoding, Credential ID 07Z60NG7YZQR) - Sep 2024
- Belajar Membuat Aplikasi Flutter untuk Pemula (Dicoding, Credential ID 81P2N089YXOY) - Sep 2024
- Belajar Prinsip Pemrograman SOLID (Dicoding, Credential ID NVP7890GOXR0) - Sep 2023
- Belajar Dasar Git dengan GitHub (Dicoding, Credential ID 07Z6VDLEYXQR) - Jul 2023
<!-- All via Dicoding Indonesia, IDCamp Scholarship -->

## References
- [NAME], [TITLE], [COMPANY] ([EMAIL], [PHONE])

More references available upon request.
