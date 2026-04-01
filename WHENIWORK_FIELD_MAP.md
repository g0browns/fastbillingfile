# When I Work Field Map

This is the authoritative reference for mapping When I Work API data to audit fields.

## How Data Connects

When I Work does NOT store client names directly on shifts. Instead:
- **Sites = Clients.** Each site represents a client or client location (e.g., "Cody McLean", "Sarah Ford").
- **Users = Staff (DSPs).** Each user is an employee who works shifts.
- **Positions = Service types.** Positions map to roles (Residential Staff, Job Coach, VocHab Staff, etc.).
- **Shifts = Scheduled work.** A shift links a user (staff) to a site (client) at a position (service type) with start/end times.
- **Times = Clock in/out (EVV).** A time entry records actual clock in/out and links back to the shift.

## Shifts (`GET /2/shifts`)

| Audit Field | Shift Field | Type | Notes |
|---|---|---|---|
| **Shift ID** | `id` | integer | Unique shift identifier |
| **Staff (who)** | `user_id` | integer | Resolve to name via `/2/users` |
| **Client (who for)** | `site_id` | integer | Resolve to client name via `/2/sites` — THIS IS THE CLIENT |
| **Location** | `location_id` | integer | Resolve via `/2/locations` (e.g., "Meadowbrook", "Ohio Job Network") |
| **Position/Service Type** | `position_id` | integer | Resolve via `/2/positions` (e.g., Residential Staff, Job Coach, VocHab Staff) |
| **Scheduled Start** | `start_time` | datetime string | Format: "Fri, 27 Mar 2026 17:30:00 -0400" |
| **Scheduled End** | `end_time` | datetime string | Same format as start_time |
| **Break Time** | `break_time` | number | Minutes of break |
| **Published** | `published` | boolean | Whether shift is visible to staff |
| **Notes** | `notes` | string | Shift notes (usually empty) |
| **Open Shift** | `is_open` | boolean | Unassigned shift available for pickup |
| **Acknowledged** | `acknowledged` | integer | Whether staff acknowledged the shift |

## DO NOT Confuse These

| Field | What It Actually Is | What It Is NOT |
|---|---|---|
| `location_id` → Locations | Your business entities ("Meadowbrook", "Ohio Job Network") | NOT the client — this is YOUR company |
| `site_id` → Sites | **The client** or client's location (e.g., "Cody McLean", "Sarah Ford") | NOT your office location |
| `user_id` → Users | **The staff member** working the shift | NOT the client |
| `position_id` → Positions | The role/service type (Residential Staff, Job Coach, etc.) | NOT a job title in the traditional sense |
| `notes` | Shift-level notes (usually empty) | NOT shift notes/service documentation |

## Time Entries — Clock In/Out (`GET /2/times`)

| Audit Field | Time Field | Type | Notes |
|---|---|---|---|
| **Time Entry ID** | `id` | integer | Unique time record |
| **Staff** | `user_id` | integer | Who clocked in |
| **Client** | `site_id` | integer | Resolve to client name via `/2/sites` |
| **Linked Shift** | `shift_id` | integer | The scheduled shift this clock-in is for |
| **Actual Clock In** | `start_time` | datetime string | When staff actually clocked in |
| **Actual Clock Out** | `end_time` | datetime string | When staff actually clocked out (null if still clocked in) |
| **Hours Worked** | `length` | float | Total hours (e.g., 11.9334) |
| **Break Hours** | `break_hours` | float | Break time in hours |
| **Position** | `position_id` | integer | Service type for this time entry |
| **Approved** | `is_approved` | boolean | Manager approval status |
| **Alert Type** | `alert_type` | integer | 0=none, 2=early/late clock, 3=early/late clock |

## Users — Staff (`GET /2/users`)

| Field | Type | Notes |
|---|---|---|
| `id` | integer | User ID — referenced by `user_id` on shifts and times |
| `first_name` | string | Staff first name |
| `last_name` | string | Staff last name |
| `email` | string | Staff email |
| `role` | integer | 1=Admin, 2=Manager, 3=Employee |

## Sites — Clients (`GET /2/sites`)

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Site ID — referenced by `site_id` on shifts and times |
| `name` | string | **Client name** (e.g., "Cody McLean", "Sarah Ford") or location name (e.g., "DAY PROGRAM") |
| `address` | string | Client's address |
| `city` | string | City |
| `state` | string | State |

## Positions — Service Types (`GET /2/positions`)

| Position Name | What It Maps To |
|---|---|
| Residential Staff | Residential/home-based care shifts |
| Job Coach | Employment support (OOD/VR services) |
| Adventure Staff | Community activities |
| VocHab Staff | Vocational Habilitation |
| NMT Staff | Non-Medical Transportation |
| Management | Admin/management (not billable) |
| Ticket to Work | Ticket to Work program |
| PRN | As-needed/on-call staff |

## Locations — Business Entities (`GET /2/locations`)

| Location Name | What It Is |
|---|---|
| Meadowbrook | Main operations (ID: 3441173) |
| Ohio Job Network | Employment services division (ID: 5345694) |

## Connecting Shift to Audit

To build a complete audit record from a single shift:

1. `shift.site_id` → look up in Sites → **Client Name**
2. `shift.user_id` → look up in Users → **Staff Name (DSP)**
3. `shift.position_id` → look up in Positions → **Service Type**
4. `shift.start_time` / `shift.end_time` → **Scheduled Hours**
5. Find matching Time Entry where `time.shift_id == shift.id` → **Actual Clock In/Out**
6. Compare scheduled vs actual times → **EVV Verification**

## Important Notes

- **Site names may not exactly match JotForm client names.** e.g., "Cody McLean" (site) vs "Cody McLean" (JotForm clientName) — normalize before matching.
- **Some sites are workplaces, not client homes.** e.g., "Jacob - KFC", "Cody Panera Bread" — these are job coaching sites.
- **Some clients have multiple sites.** e.g., "Cody McLean", "Cody Panera Bread", "Cody (Cliffside)" are all the same client at different locations.
- **Time entries link to shifts via `shift_id`.** This is how you verify clock-in matches the schedule.
- **Times may not exist** if staff forgot to clock in/out — this is itself an audit flag.
- **`length` on time entries** is actual hours worked, calculated from clock in/out.
- **Authentication:** Login at `https://api.login.wheniwork.com/login` with email/password + W-Key header, returns token for `W-Token` header on all subsequent calls.
