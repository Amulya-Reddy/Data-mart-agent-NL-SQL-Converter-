"""
Generates a fully synthetic anesthesia billing/reconciliation data mart as a
local SQLite file. No real patients, providers, facilities, or claims —
everything here is fabricated with a fixed random seed for reproducibility.

Run:
    python demo_data/seed_demo_data.py
"""
import os
import random
import sqlite3
from datetime import datetime, timedelta

SEED = 20240601
random.seed(SEED)

DB_PATH = os.path.join(os.path.dirname(__file__), "ncap_demo.db")

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

FACILITIES = [
    ("RVH", "Riverview Hospital", "Riverview", "OH"),
    ("SPM", "St. Pinewood Medical Center", "Pinewood", "PA"),
    ("LKC", "Lakeside Surgical Center", "Lakeside", "MI"),
    ("WMC", "Westbrook Medical Center", "Westbrook", "IN"),
]

SURGEON_SPECIALTIES = [
    "Orthopedic", "General", "Cardiothoracic", "OB/GYN", "Neurosurgery",
    "Urology", "ENT",
]

FIRST_NAMES = [
    "James", "Maria", "David", "Linda", "Robert", "Susan", "Michael", "Karen",
    "William", "Nancy", "Richard", "Betty", "Joseph", "Sandra", "Thomas",
    "Ashley", "Charles", "Kimberly", "Daniel", "Emily", "Matthew", "Donna",
    "Anthony", "Michelle", "Mark", "Carol", "Paul", "Amanda", "Steven",
    "Melissa", "Andrew", "Deborah", "Kenneth", "Stephanie", "George",
    "Rebecca", "Joshua", "Laura", "Kevin", "Sharon", "Brian", "Cynthia",
    "Edward", "Kathleen", "Ronald", "Amy", "Timothy", "Angela", "Jason",
    "Shirley",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
]

PAYERS = [
    ("Aetna", "Commercial"),
    ("Blue Cross Blue Shield", "Commercial"),
    ("UnitedHealthcare", "Commercial"),
    ("Cigna", "Commercial"),
    ("Humana", "Commercial"),
    ("Medicare", "Medicare"),
    ("Medicaid", "Medicaid"),
    ("Self-Pay", "SelfPay"),
]

# Weighted insurance mix for patients: commercial-heavy, then Medicare/Medicaid,
# small self-pay slice.
INSURANCE_WEIGHTS = [
    ("Aetna", 14), ("Blue Cross Blue Shield", 16), ("UnitedHealthcare", 14),
    ("Cigna", 10), ("Humana", 8), ("Medicare", 20), ("Medicaid", 12),
    ("Self-Pay", 6),
]

# Anesthesia CPT code ranges (00100-01999) by surgical specialty, with a
# representative description for each.
PROCEDURES_BY_SPECIALTY = {
    "Orthopedic": [
        ("01402", "Anesthesia for total knee arthroplasty"),
        ("01214", "Anesthesia for total hip arthroplasty"),
        ("01480", "Anesthesia for procedure on forearm/wrist/hand bones"),
        ("01610", "Anesthesia for procedure on shoulder joint"),
    ],
    "General": [
        ("00840", "Anesthesia for intraperitoneal procedures, lower abdomen"),
        ("00790", "Anesthesia for intraperitoneal procedures, upper abdomen"),
        ("00810", "Anesthesia for lower intestinal endoscopic procedures"),
        ("00450", "Anesthesia for procedures on integumentary system"),
    ],
    "Cardiothoracic": [
        ("00560", "Anesthesia for procedures on heart, pericardium"),
        ("00580", "Anesthesia for heart transplant/cardiopulmonary bypass"),
        ("00542", "Anesthesia for thoracotomy procedures"),
    ],
    "OB/GYN": [
        ("01961", "Anesthesia for cesarean delivery"),
        ("00840", "Anesthesia for intraperitoneal procedures, lower abdomen"),
        ("00944", "Anesthesia for vaginal hysterectomy"),
    ],
    "Neurosurgery": [
        ("00211", "Anesthesia for intracranial procedures"),
        ("00600", "Anesthesia for procedures on spine, cervical"),
        ("00630", "Anesthesia for procedures on spine, lumbar"),
    ],
    "Urology": [
        ("00918", "Anesthesia for transurethral procedures"),
        ("00862", "Anesthesia for procedures on kidney/ureter"),
        ("00920", "Anesthesia for procedures on male genitalia"),
    ],
    "ENT": [
        ("00160", "Anesthesia for procedures on nose/sinuses"),
        ("00170", "Anesthesia for intraoral procedures"),
        ("00126", "Anesthesia for tympanotomy"),
    ],
}

DENIAL_CODES = [
    ("CO-50", "Not deemed a medical necessity"),
    ("CO-16", "Claim lacks information needed for adjudication"),
    ("PR-1", "Deductible not yet met"),
    ("CO-97", "Benefit included in another service already adjudicated"),
    ("CO-29", "Time limit for filing has expired"),
]

STATUSES_SCHEDULE = ["Completed", "Cancelled", "No-Show", "Scheduled"]
STATUSES_SCHEDULE_WEIGHTS = [80, 8, 5, 7]

ASA_CLASSES = ["I", "II", "III", "IV", "V"]
ASA_WEIGHTS = [18, 38, 32, 10, 2]

RATE_PER_UNIT_MIN = 70.0
RATE_PER_UNIT_MAX = 75.0


def rand_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def synthetic_npi(used: set) -> str:
    while True:
        npi = "".join(str(random.randint(0, 9)) for _ in range(10))
        if npi not in used:
            used.add(npi)
            return npi


def synthetic_mrn(used: set) -> str:
    while True:
        mrn = f"MRN{random.randint(100000, 999999)}"
        if mrn not in used:
            used.add(mrn)
            return mrn


def build_schema(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE dim_Facility (
            FacilityID INTEGER PRIMARY KEY,
            FacilityCode TEXT NOT NULL UNIQUE,
            FacilityName TEXT NOT NULL,
            City TEXT NOT NULL,
            State TEXT NOT NULL
        );

        CREATE TABLE dim_Provider (
            ProviderID INTEGER PRIMARY KEY,
            NPI TEXT NOT NULL UNIQUE,
            FirstName TEXT NOT NULL,
            LastName TEXT NOT NULL,
            ProviderRole TEXT NOT NULL CHECK (ProviderRole IN ('Anesthesiologist','CRNA','Surgeon')),
            Specialty TEXT,
            FacilityID INTEGER NOT NULL REFERENCES dim_Facility(FacilityID),
            ActiveFlag INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE dim_Payer (
            PayerID INTEGER PRIMARY KEY,
            PayerName TEXT NOT NULL,
            PayerType TEXT NOT NULL CHECK (PayerType IN ('Commercial','Medicare','Medicaid','SelfPay'))
        );

        CREATE TABLE dim_Patient (
            PatientID INTEGER PRIMARY KEY,
            MRN TEXT NOT NULL UNIQUE,
            FirstName TEXT NOT NULL,
            LastName TEXT NOT NULL,
            DOB TEXT NOT NULL,
            Gender TEXT NOT NULL,
            InsuranceProvider TEXT NOT NULL,
            InsuranceID TEXT,
            FacilityID INTEGER NOT NULL REFERENCES dim_Facility(FacilityID)
        );

        CREATE TABLE fact_Schedule (
            ScheduleID INTEGER PRIMARY KEY,
            PatientID INTEGER NOT NULL REFERENCES dim_Patient(PatientID),
            ProviderID INTEGER NOT NULL REFERENCES dim_Provider(ProviderID),
            FacilityID INTEGER NOT NULL REFERENCES dim_Facility(FacilityID),
            ScheduledDate TEXT NOT NULL,
            ScheduledProcedure TEXT NOT NULL,
            ORRoom TEXT NOT NULL,
            Status TEXT NOT NULL CHECK (Status IN ('Scheduled','Completed','Cancelled','No-Show'))
        );

        CREATE TABLE fact_Surgery (
            CaseID INTEGER PRIMARY KEY,
            ScheduleID INTEGER NOT NULL REFERENCES fact_Schedule(ScheduleID),
            PatientID INTEGER NOT NULL REFERENCES dim_Patient(PatientID),
            SurgeonID INTEGER NOT NULL REFERENCES dim_Provider(ProviderID),
            AnesthesiaProviderID INTEGER NOT NULL REFERENCES dim_Provider(ProviderID),
            FacilityID INTEGER NOT NULL REFERENCES dim_Facility(FacilityID),
            DateOfService TEXT NOT NULL,
            ASAClass TEXT NOT NULL,
            ProcedureCode TEXT NOT NULL,
            ProcedureDescription TEXT NOT NULL,
            AnesthesiaStartTime TEXT NOT NULL,
            AnesthesiaEndTime TEXT NOT NULL,
            AnesthesiaMinutes INTEGER NOT NULL,
            CaseStatus TEXT NOT NULL CHECK (CaseStatus IN ('Completed','Cancelled','In-Progress'))
        );

        CREATE TABLE fact_Billing (
            TransactionID INTEGER PRIMARY KEY,
            CaseID INTEGER NOT NULL REFERENCES fact_Surgery(CaseID),
            TransactionType TEXT NOT NULL CHECK (TransactionType IN ('Charge','Payment','Adjustment')),
            TransactionDate TEXT NOT NULL,
            CPTCode TEXT NOT NULL,
            Units REAL NOT NULL,
            ChargeAmount REAL NOT NULL DEFAULT 0,
            PaidAmount REAL NOT NULL DEFAULT 0,
            AdjustmentAmount REAL NOT NULL DEFAULT 0,
            Balance REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE fact_Claims (
            ClaimID INTEGER PRIMARY KEY,
            CaseID INTEGER NOT NULL REFERENCES fact_Surgery(CaseID),
            PayerID INTEGER NOT NULL REFERENCES dim_Payer(PayerID),
            ClaimNumber TEXT NOT NULL UNIQUE,
            ClaimSubmitDate TEXT NOT NULL,
            ClaimStatus TEXT NOT NULL CHECK (ClaimStatus IN ('Submitted','Paid','Denied','Pending','Appealed')),
            BilledAmount REAL NOT NULL,
            AllowedAmount REAL,
            PaidAmount REAL,
            DenialReasonCode TEXT,
            DenialReason TEXT
        );
        """
    )
    conn.commit()


def seed_facilities(conn):
    cur = conn.cursor()
    rows = [(i + 1, code, name, city, state) for i, (code, name, city, state) in enumerate(FACILITIES)]
    cur.executemany(
        "INSERT INTO dim_Facility (FacilityID, FacilityCode, FacilityName, City, State) VALUES (?,?,?,?,?)",
        rows,
    )
    conn.commit()
    return {code: fid for fid, code, *_ in rows}


def seed_providers(conn, facility_ids):
    cur = conn.cursor()
    used_npi = set()
    provider_id = 1
    rows = []
    provider_meta = {}  # provider_id -> dict(role, specialty, facility_id)

    for code, fid in facility_ids.items():
        specialties = random.sample(SURGEON_SPECIALTIES, k=random.randint(2, 3))
        for spec in specialties:
            fn, ln = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
            npi = synthetic_npi(used_npi)
            rows.append((provider_id, npi, fn, ln, "Surgeon", spec, fid, 1))
            provider_meta[provider_id] = {"role": "Surgeon", "specialty": spec, "facility_id": fid}
            provider_id += 1

        for _ in range(random.randint(1, 2)):
            fn, ln = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
            npi = synthetic_npi(used_npi)
            rows.append((provider_id, npi, fn, ln, "Anesthesiologist", None, fid, 1))
            provider_meta[provider_id] = {"role": "Anesthesiologist", "specialty": None, "facility_id": fid}
            provider_id += 1

        for _ in range(random.randint(1, 2)):
            fn, ln = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
            npi = synthetic_npi(used_npi)
            rows.append((provider_id, npi, fn, ln, "CRNA", None, fid, 1))
            provider_meta[provider_id] = {"role": "CRNA", "specialty": None, "facility_id": fid}
            provider_id += 1

    cur.executemany(
        "INSERT INTO dim_Provider (ProviderID, NPI, FirstName, LastName, ProviderRole, Specialty, FacilityID, ActiveFlag) "
        "VALUES (?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    return provider_meta


def seed_payers(conn):
    cur = conn.cursor()
    rows = [(i + 1, name, ptype) for i, (name, ptype) in enumerate(PAYERS)]
    cur.executemany("INSERT INTO dim_Payer (PayerID, PayerName, PayerType) VALUES (?,?,?)", rows)
    conn.commit()
    return {name: pid for pid, name, _ in rows}, {pid: ptype for pid, _, ptype in rows}


def seed_patients(conn, facility_ids, n=500):
    cur = conn.cursor()
    used_mrn = set()
    facility_id_list = list(facility_ids.values())
    insurance_choices = [name for name, _w in INSURANCE_WEIGHTS]
    insurance_weights = [w for _name, w in INSURANCE_WEIGHTS]

    rows = []
    dob_start = datetime(1935, 1, 1)
    dob_end = datetime(2006, 1, 1)
    for pid in range(1, n + 1):
        fn, ln = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
        mrn = synthetic_mrn(used_mrn)
        dob = rand_date(dob_start, dob_end).strftime("%Y-%m-%d")
        gender = random.choice(["M", "F"])
        insurance = random.choices(insurance_choices, weights=insurance_weights, k=1)[0]
        insurance_id = None if insurance == "Self-Pay" else f"INS{random.randint(10000000, 99999999)}"
        fid = random.choice(facility_id_list)
        rows.append((pid, mrn, fn, ln, dob, gender, insurance, insurance_id, fid))

    cur.executemany(
        "INSERT INTO dim_Patient (PatientID, MRN, FirstName, LastName, DOB, Gender, InsuranceProvider, InsuranceID, FacilityID) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    return rows


def seed_schedule_and_surgery(conn, patients, provider_meta, n=1000):
    cur = conn.cursor()

    surgeons_by_facility = {}
    anesthesia_by_facility = {}
    for pid, meta in provider_meta.items():
        fid = meta["facility_id"]
        if meta["role"] == "Surgeon":
            surgeons_by_facility.setdefault(fid, []).append(pid)
        else:
            anesthesia_by_facility.setdefault(fid, []).append(pid)

    or_rooms = [f"OR-{i}" for i in range(1, 7)]
    today = datetime(2026, 8, 14)
    window_start = today - timedelta(days=365)
    window_end = today + timedelta(days=21)  # small slice of future "Scheduled" cases

    eligible_patients = [
        p for p in patients
        if surgeons_by_facility.get(p[8]) and anesthesia_by_facility.get(p[8])
    ]

    schedule_rows = []
    surgery_rows = []
    case_id = 1

    for schedule_id in range(1, n + 1):
        patient = random.choice(eligible_patients)
        patient_id = patient[0]
        facility_id = patient[8]
        surgeons = surgeons_by_facility[facility_id]
        anesthesiologists = anesthesia_by_facility[facility_id]

        surgeon_id = random.choice(surgeons)
        specialty = provider_meta[surgeon_id]["specialty"]
        cpt_code, cpt_desc = random.choice(PROCEDURES_BY_SPECIALTY[specialty])

        scheduled_dt = rand_date(window_start, window_end)
        status = random.choices(STATUSES_SCHEDULE, weights=STATUSES_SCHEDULE_WEIGHTS, k=1)[0]
        # Future dates can't already be Completed/Cancelled/No-Show in a sane demo.
        if scheduled_dt > today:
            status = "Scheduled"

        or_room = random.choice(or_rooms)
        schedule_rows.append(
            (schedule_id, patient_id, surgeon_id, facility_id,
             scheduled_dt.strftime("%Y-%m-%d"), cpt_desc, or_room, status)
        )

        if status == "Completed":
            anesthesia_provider_id = random.choice(anesthesiologists)
            case_status = random.choices(
                ["Completed", "Cancelled", "In-Progress"], weights=[94, 4, 2], k=1
            )[0]
            asa_class = random.choices(ASA_CLASSES, weights=ASA_WEIGHTS, k=1)[0]

            start_hour = random.randint(6, 15)
            start_minute = random.choice([0, 15, 30, 45])
            anes_start = scheduled_dt.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
            duration_minutes = max(30, int(random.gauss(120, 45)))
            anes_end = anes_start + timedelta(minutes=duration_minutes)

            surgery_rows.append(
                (case_id, schedule_id, patient_id, surgeon_id, anesthesia_provider_id,
                 facility_id, scheduled_dt.strftime("%Y-%m-%d"), asa_class, cpt_code, cpt_desc,
                 anes_start.strftime("%Y-%m-%d %H:%M:%S"), anes_end.strftime("%Y-%m-%d %H:%M:%S"),
                 duration_minutes, case_status)
            )
            case_id += 1

    cur.executemany(
        "INSERT INTO fact_Schedule (ScheduleID, PatientID, ProviderID, FacilityID, ScheduledDate, "
        "ScheduledProcedure, ORRoom, Status) VALUES (?,?,?,?,?,?,?,?)",
        schedule_rows,
    )
    cur.executemany(
        "INSERT INTO fact_Surgery (CaseID, ScheduleID, PatientID, SurgeonID, AnesthesiaProviderID, FacilityID, "
        "DateOfService, ASAClass, ProcedureCode, ProcedureDescription, AnesthesiaStartTime, AnesthesiaEndTime, "
        "AnesthesiaMinutes, CaseStatus) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        surgery_rows,
    )
    conn.commit()
    return surgery_rows


def seed_billing_and_claims(conn, surgery_rows, patients_by_id, payer_ids, payer_types):
    cur = conn.cursor()

    billing_rows = []
    claims_rows = []
    transaction_id = 1
    claim_id = 1
    claim_numbers_used = set()

    for surgery in surgery_rows:
        (case_id, _schedule_id, patient_id, _surgeon_id, _anes_id, _facility_id,
         dos, _asa, cpt_code, _desc, _start, _end, minutes, case_status) = surgery

        if case_status != "Completed":
            continue

        base_units = 5  # simplified base-unit value per CPT range for the demo
        time_units = round(minutes / 15.0, 1)
        total_units = round(base_units + time_units, 1)
        rate = round(random.uniform(RATE_PER_UNIT_MIN, RATE_PER_UNIT_MAX), 2)
        charge_amount = round(total_units * rate, 2)

        dos_dt = datetime.strptime(dos, "%Y-%m-%d")
        charge_date = dos_dt + timedelta(days=1)

        patient = patients_by_id[patient_id]
        insurance_name = patient[6]
        payer_id = payer_ids[insurance_name]
        payer_type = payer_types[payer_id]

        claim_status = random.choices(
            ["Paid", "Pending", "Denied", "Submitted", "Appealed"],
            weights=[55, 13, 14, 11, 7],
            k=1,
        )[0]

        submit_date = charge_date + timedelta(days=random.randint(1, 5))
        billed_amount = charge_amount

        allowed_amount = None
        paid_amount = None
        denial_code = None
        denial_reason = None

        paid_line_amount = 0.0
        adjustment_line_amount = 0.0

        if claim_status == "Paid":
            allowance_rate = random.uniform(0.55, 0.85) if payer_type == "Commercial" else random.uniform(0.4, 0.6)
            allowed_amount = round(billed_amount * allowance_rate, 2)
            paid_amount = round(allowed_amount * random.uniform(0.85, 1.0), 2)
            paid_line_amount = paid_amount
            adjustment_line_amount = round(billed_amount - paid_amount, 2)
        elif claim_status == "Denied":
            denial_code, denial_reason = random.choice(DENIAL_CODES)
            allowed_amount = 0.0
            paid_amount = 0.0
            adjustment_line_amount = round(billed_amount, 2)
        elif claim_status == "Appealed":
            denial_code, denial_reason = random.choice(DENIAL_CODES)
            allowed_amount = round(billed_amount * random.uniform(0.3, 0.6), 2)
            paid_amount = None  # still pending resolution
        # Pending / Submitted: allowed/paid remain NULL, nothing posted yet.

        while True:
            claim_number = f"CLM{random.randint(1000000, 9999999)}"
            if claim_number not in claim_numbers_used:
                claim_numbers_used.add(claim_number)
                break

        claims_rows.append(
            (claim_id, case_id, payer_id, claim_number, submit_date.strftime("%Y-%m-%d"),
             claim_status, billed_amount, allowed_amount, paid_amount, denial_code, denial_reason)
        )
        claim_id += 1

        # Billing lines: always a Charge; Payment + Adjustment only when money actually posted.
        balance_after_charge = charge_amount - paid_line_amount - adjustment_line_amount
        billing_rows.append(
            (transaction_id, case_id, "Charge", charge_date.strftime("%Y-%m-%d"), cpt_code,
             total_units, charge_amount, 0.0, 0.0, round(charge_amount, 2))
        )
        transaction_id += 1

        if paid_line_amount > 0:
            payment_date = submit_date + timedelta(days=random.randint(14, 45))
            billing_rows.append(
                (transaction_id, case_id, "Payment", payment_date.strftime("%Y-%m-%d"), cpt_code,
                 0, 0.0, paid_line_amount, 0.0, round(balance_after_charge, 2))
            )
            transaction_id += 1

        if adjustment_line_amount > 0:
            adj_date = submit_date + timedelta(days=random.randint(14, 45))
            billing_rows.append(
                (transaction_id, case_id, "Adjustment", adj_date.strftime("%Y-%m-%d"), cpt_code,
                 0, 0.0, 0.0, adjustment_line_amount, round(balance_after_charge, 2))
            )
            transaction_id += 1

    cur.executemany(
        "INSERT INTO fact_Billing (TransactionID, CaseID, TransactionType, TransactionDate, CPTCode, Units, "
        "ChargeAmount, PaidAmount, AdjustmentAmount, Balance) VALUES (?,?,?,?,?,?,?,?,?,?)",
        billing_rows,
    )
    cur.executemany(
        "INSERT INTO fact_Claims (ClaimID, CaseID, PayerID, ClaimNumber, ClaimSubmitDate, ClaimStatus, "
        "BilledAmount, AllowedAmount, PaidAmount, DenialReasonCode, DenialReason) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        claims_rows,
    )
    conn.commit()
    return billing_rows, claims_rows


def verify(conn):
    cur = conn.cursor()
    tables = [
        "dim_Facility", "dim_Provider", "dim_Payer", "dim_Patient",
        "fact_Schedule", "fact_Surgery", "fact_Billing", "fact_Claims",
    ]
    print("\nRow counts:")
    for t in tables:
        count = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:16s} {count}")

    print("\nReferential integrity checks:")
    checks = [
        ("fact_Schedule.PatientID -> dim_Patient", "SELECT COUNT(*) FROM fact_Schedule s LEFT JOIN dim_Patient p ON s.PatientID=p.PatientID WHERE p.PatientID IS NULL"),
        ("fact_Schedule.ProviderID -> dim_Provider", "SELECT COUNT(*) FROM fact_Schedule s LEFT JOIN dim_Provider p ON s.ProviderID=p.ProviderID WHERE p.ProviderID IS NULL"),
        ("fact_Schedule.FacilityID -> dim_Facility", "SELECT COUNT(*) FROM fact_Schedule s LEFT JOIN dim_Facility f ON s.FacilityID=f.FacilityID WHERE f.FacilityID IS NULL"),
        ("fact_Surgery.ScheduleID -> fact_Schedule", "SELECT COUNT(*) FROM fact_Surgery s LEFT JOIN fact_Schedule sc ON s.ScheduleID=sc.ScheduleID WHERE sc.ScheduleID IS NULL"),
        ("fact_Surgery.SurgeonID -> dim_Provider", "SELECT COUNT(*) FROM fact_Surgery s LEFT JOIN dim_Provider p ON s.SurgeonID=p.ProviderID WHERE p.ProviderID IS NULL"),
        ("fact_Surgery.AnesthesiaProviderID -> dim_Provider", "SELECT COUNT(*) FROM fact_Surgery s LEFT JOIN dim_Provider p ON s.AnesthesiaProviderID=p.ProviderID WHERE p.ProviderID IS NULL"),
        ("fact_Billing.CaseID -> fact_Surgery", "SELECT COUNT(*) FROM fact_Billing b LEFT JOIN fact_Surgery s ON b.CaseID=s.CaseID WHERE s.CaseID IS NULL"),
        ("fact_Claims.CaseID -> fact_Surgery", "SELECT COUNT(*) FROM fact_Claims c LEFT JOIN fact_Surgery s ON c.CaseID=s.CaseID WHERE s.CaseID IS NULL"),
        ("fact_Claims.PayerID -> dim_Payer", "SELECT COUNT(*) FROM fact_Claims c LEFT JOIN dim_Payer p ON c.PayerID=p.PayerID WHERE p.PayerID IS NULL"),
    ]
    all_ok = True
    for label, sql in checks:
        orphans = cur.execute(sql).fetchone()[0]
        ok = orphans == 0
        all_ok = all_ok and ok
        print(f"  [{'OK' if ok else 'FAIL'}] {label}: {orphans} orphaned rows")

    # Reconciliation only holds for claims whose adjudication is fully resolved
    # (Paid or Denied). Pending/Submitted/Appealed cases correctly carry a
    # nonzero outstanding balance until resolved.
    charge_check = cur.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT b.CaseID,
                   ROUND(SUM(CASE WHEN b.TransactionType='Charge' THEN b.ChargeAmount
                                  WHEN b.TransactionType='Payment' THEN -b.PaidAmount
                                  WHEN b.TransactionType='Adjustment' THEN -b.AdjustmentAmount END), 2) AS net
            FROM fact_Billing b
            JOIN fact_Claims c ON b.CaseID = c.CaseID
            WHERE c.ClaimStatus IN ('Paid', 'Denied')
            GROUP BY b.CaseID
            HAVING ABS(net) > 0.02
        )
        """
    ).fetchone()[0]
    ok = charge_check == 0
    all_ok = all_ok and ok
    print(f"  [{'OK' if ok else 'FAIL'}] Billing reconciliation for resolved (Paid/Denied) claims: {charge_check} unbalanced cases")

    if not all_ok:
        raise SystemExit("Data integrity checks failed.")
    print("\nAll integrity checks passed.")


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    build_schema(conn)
    facility_ids = seed_facilities(conn)
    provider_meta = seed_providers(conn, facility_ids)
    payer_ids, payer_types = seed_payers(conn)
    patients = seed_patients(conn, facility_ids, n=500)
    patients_by_id = {p[0]: p for p in patients}
    surgery_rows = seed_schedule_and_surgery(conn, patients, provider_meta, n=1000)
    seed_billing_and_claims(conn, surgery_rows, patients_by_id, payer_ids, payer_types)

    verify(conn)
    conn.close()
    print(f"\nSeeded synthetic data mart at: {DB_PATH}")


if __name__ == "__main__":
    main()
