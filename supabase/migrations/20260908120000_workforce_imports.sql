-- Governed employee, attendance, manpower, and deployment import storage.
SET LOCAL search_path = prosight,extensions,pg_catalog;

CREATE TABLE employees (
    employee_id TEXT PRIMARY KEY, synthetic_name TEXT NOT NULL, role TEXT NOT NULL,
    department TEXT NOT NULL, home_project_id TEXT NOT NULL,
    employment_type TEXT NOT NULL, join_date TEXT NOT NULL,
    basic_aed DOUBLE PRECISION NOT NULL, allowance_aed DOUBLE PRECISION NOT NULL,
    gross_monthly_aed DOUBLE PRECISION NOT NULL, status TEXT NOT NULL,
    data_origin TEXT, data_json TEXT NOT NULL, updated_at TEXT NOT NULL,
    import_id TEXT NOT NULL
);
CREATE INDEX idx_employees_home_project ON employees(home_project_id);

CREATE TABLE employee_training (
    training_id TEXT PRIMARY KEY, employee_id TEXT NOT NULL, course TEXT NOT NULL,
    completed_date TEXT NOT NULL, expiry_date TEXT, status TEXT NOT NULL,
    evidence_id TEXT, data_json TEXT NOT NULL, updated_at TEXT NOT NULL,
    import_id TEXT NOT NULL
);
CREATE INDEX idx_training_employee ON employee_training(employee_id);

CREATE TABLE attendance_records (
    timesheet_id TEXT PRIMARY KEY, employee_id TEXT NOT NULL, project_id TEXT NOT NULL,
    work_date TEXT NOT NULL, attendance_status TEXT NOT NULL,
    regular_hours DOUBLE PRECISION NOT NULL, ot_hours DOUBLE PRECISION NOT NULL,
    total_hours DOUBLE PRECISION NOT NULL, data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL, import_id TEXT NOT NULL
);
CREATE INDEX idx_attendance_project_date ON attendance_records(project_id,work_date);
CREATE INDEX idx_attendance_employee_date ON attendance_records(employee_id,work_date);

CREATE TABLE payroll_records (
    payroll_id TEXT PRIMARY KEY, employee_id TEXT NOT NULL, project_id TEXT NOT NULL,
    month TEXT NOT NULL, basic_aed DOUBLE PRECISION NOT NULL,
    allowance_aed DOUBLE PRECISION NOT NULL, ot_hours DOUBLE PRECISION NOT NULL,
    ot_rate_aed DOUBLE PRECISION NOT NULL, ot_pay_aed DOUBLE PRECISION NOT NULL,
    gross_aed DOUBLE PRECISION NOT NULL, employer_burden_aed DOUBLE PRECISION NOT NULL,
    total_cost_aed DOUBLE PRECISION NOT NULL, payment_date TEXT NOT NULL,
    days_worked INTEGER NOT NULL, paid_leave_days INTEGER NOT NULL,
    data_json TEXT NOT NULL, updated_at TEXT NOT NULL, import_id TEXT NOT NULL
);
CREATE INDEX idx_payroll_project_month ON payroll_records(project_id,month);

CREATE TABLE direct_allocations (
    employee_id TEXT NOT NULL, project_id TEXT NOT NULL, month TEXT NOT NULL,
    fte_allocation DOUBLE PRECISION NOT NULL, regular_hours DOUBLE PRECISION NOT NULL,
    ot_hours DOUBLE PRECISION NOT NULL, payroll_cost_aed DOUBLE PRECISION NOT NULL,
    basis TEXT, data_json TEXT NOT NULL, updated_at TEXT NOT NULL,
    import_id TEXT NOT NULL, PRIMARY KEY(employee_id,project_id,month)
);
CREATE INDEX idx_direct_allocation_project_month ON direct_allocations(project_id,month);

CREATE TABLE subcontract_crews (
    subcontract_id TEXT NOT NULL, project_id TEXT NOT NULL, vendor_id TEXT NOT NULL,
    month TEXT NOT NULL, trade TEXT NOT NULL, planned_workers INTEGER NOT NULL,
    actual_workers INTEGER NOT NULL, worker_variance INTEGER NOT NULL,
    available_labor_hours DOUBLE PRECISION NOT NULL, definition TEXT,
    data_json TEXT NOT NULL, updated_at TEXT NOT NULL, import_id TEXT NOT NULL,
    PRIMARY KEY(subcontract_id,project_id,month)
);
CREATE INDEX idx_subcontract_project_month ON subcontract_crews(project_id,month);

CREATE TABLE deployment_forecasts (
    project_id TEXT NOT NULL, month TEXT NOT NULL, direct_headcount INTEGER NOT NULL,
    subcontract_workers INTEGER NOT NULL, basis TEXT, data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL, import_id TEXT NOT NULL,
    PRIMARY KEY(project_id,month)
);
CREATE INDEX idx_deployment_project_month ON deployment_forecasts(project_id,month);

ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON employees TO prosight_backend USING (true) WITH CHECK (true);
ALTER TABLE employee_training ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_training FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON employee_training TO prosight_backend USING (true) WITH CHECK (true);
ALTER TABLE attendance_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_records FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON attendance_records TO prosight_backend USING (true) WITH CHECK (true);
ALTER TABLE payroll_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_records FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON payroll_records TO prosight_backend USING (true) WITH CHECK (true);
ALTER TABLE direct_allocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE direct_allocations FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON direct_allocations TO prosight_backend USING (true) WITH CHECK (true);
ALTER TABLE subcontract_crews ENABLE ROW LEVEL SECURITY;
ALTER TABLE subcontract_crews FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON subcontract_crews TO prosight_backend USING (true) WITH CHECK (true);
ALTER TABLE deployment_forecasts ENABLE ROW LEVEL SECURITY;
ALTER TABLE deployment_forecasts FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON deployment_forecasts TO prosight_backend USING (true) WITH CHECK (true);

GRANT SELECT,INSERT,UPDATE,DELETE ON employees,employee_training,attendance_records,
    payroll_records,direct_allocations,subcontract_crews,deployment_forecasts
    TO prosight_backend;
INSERT INTO schema_version(version) VALUES (2);
