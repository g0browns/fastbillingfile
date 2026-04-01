# JotForm Shift Note Field Map

This is the authoritative reference for mapping JotForm form fields to audit data.
Use this to avoid misidentifying fields (e.g., reading a mood dropdown as a client name).

## Critical Audit Fields

| Audit Field | JotForm `name` | Question ID (example) | Type | Notes |
|---|---|---|---|---|
| **Client Name** | `clientName` | Q118 | `control_dropdown` | The individual receiving services. Always a dropdown. |
| **Session Date** | `sessionDate73` | Q73 | `control_datetime` | Date of service. Answer is object with `month`, `day`, `year`, `datetime`. Also has `prettyFormat`. |
| **Medicaid ID** | `medId` | Q128 | `control_number` | Individual's Medicaid ID. Must match billing claims. |
| **Service Code** | `serviceCode` | Q117 | `control_textbox` | e.g., APC, ADS, VH, IES, GES. Must match billing. |
| **Service Description** | `service` | Q127 | `control_textbox` | e.g., "Homemaker/Personal Care". Human-readable service type. |
| **Units** | `units` | Q86 | `control_number` | Units of service. Must match billing units. |
| **Shift Time** | `shiftTime` | Q90 | `control_time` | Start and end time with duration. Answer has `hourSelect`, `minuteSelect`, `ampm`, `hourSelectRange`, `minuteSelectRange`, `ampmRange`, `timeRangeDuration`. |
| **DSP Staff Name** | `dspStaff` | Q81 | `control_fullname` | The person who provided the service. Answer has `first`, `last`, `prettyFormat`. |
| **Signature** | `signature` | Q93 | `control_signature` | Provider's signature. Answer is a URL to the signature image. |
| **Shift Activities** | `shiftActivities` | Q78 | `control_textarea` | Narrative description of what happened during the shift. |

## Supporting Fields

| Audit Field | JotForm `name` | Question ID (example) | Type | Notes |
|---|---|---|---|---|
| **Service Location** | `serviceLocation` | Q87 | `control_dropdown` | Where service was provided. |
| **County** | `county` | Q115 | `control_textbox` | County of service. |
| **Rate** | `rate` | Q116 | `control_number` | Billing rate. |
| **Group Size** | `group` | Q113 | `control_number` | Number of individuals in group. |
| **Staff Count** | `staff` | Q114 | `control_number` | Number of staff present. |
| **Contract** | `contract137` | Q137 | `control_textbox` | Contract number. |
| **Total Miles** | `totalMiles` | Q138 | `control_number` | Miles traveled with client. |
| **Email** | `email` | Q131 | `control_email` | Staff email address. |

## DO NOT Confuse These Fields

| Field | `name` | What It Actually Is | What It Is NOT |
|---|---|---|---|
| **Client Mood** | `clientMood` (Q43) | `control_dropdown` — mood observation (e.g., "Happy", "Sad", "Anxious") | NOT a client name |
| **Form Header** | `clickTo` (Q1) | `control_head` — form title (e.g., "Shift Notes - Cody McLean") | NOT a data field |
| **Section Headers** | `clickTo57`, `clickTo59`, `clickTo71` | `control_collapse` — collapsible section labels | NOT data fields |
| **Submit Button** | `submit` (Q35) | `control_button` | NOT a data field |
| **Inline Fields** | `input135` (Q135) | `control_inline` — sub-fields with generic keys like `shorttext-1` | Purpose unclear, do not rely on |

## Services & Supports Radio Questions

These are Yes/No/Not needed questions specific to each individual's care plan:

| Question ID (example) | `name` | Typical Question Pattern |
|---|---|---|
| Q141 | `didStaff141` | Medical appointments assistance |
| Q177 | `didYou177` | Errands assistance |
| Q178 | `didStaff178` | Community activity transport |
| Q179 | `didStaff179` | Domestic care assistance |

These vary per individual form but follow the `didStaff` / `didYou` naming pattern.

## Important Notes

- **One form per individual.** There are 30+ forms, each named "[Name] - Shift Note".
- **Question IDs may differ between forms** but field `name` values are consistent.
- **Match on `name` not question ID** when extracting data across forms.
- **Session date answer is an object**, not a string. Use `answer.month/day/year` or `prettyFormat`.
- **Shift time answer is an object** with separate start/end components and `timeRangeDuration`.
- **DSP staff name answer is an object** with `first`, `last`, and `prettyFormat`.
- **HIPAA endpoint required:** Use `https://hipaa-api.jotform.com`, not `https://api.jotform.com`.
