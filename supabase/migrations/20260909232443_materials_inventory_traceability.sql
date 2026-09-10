-- Normalized material master, inventory balances, and immutable movement traceability.
-- This migration is additive and does not modify legacy prosight objects.

begin;

create table construction.material_items (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    material_code text not null check (length(btrim(material_code)) > 0),
    name text not null check (length(btrim(name)) > 0),
    description text,
    category text,
    unit_code text not null check (length(btrim(unit_code)) > 0),
    manufacturer text,
    manufacturer_part_number text,
    specification jsonb not null default '{}'::jsonb
        check (jsonb_typeof(specification) = 'object'),
    reorder_quantity numeric(20,6) not null default 0 check (reorder_quantity >= 0),
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid references auth.users(id) on delete set null,
    updated_by uuid references auth.users(id) on delete set null,
    unique (organization_id, material_code),
    unique (organization_id, id)
);

create table construction.inventory_locations (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    location_code text not null check (length(btrim(location_code)) > 0),
    name text not null check (length(btrim(name)) > 0),
    location_type text not null default 'store'
        check (location_type in ('warehouse','store','laydown','site','vehicle','other')),
    description text,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid references auth.users(id) on delete set null,
    updated_by uuid references auth.users(id) on delete set null,
    foreign key (organization_id, project_id)
        references construction.projects(organization_id, id) on delete restrict,
    unique (organization_id, project_scope_id, location_code),
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id)
);

create table construction.material_inventory_balances (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    inventory_location_id uuid not null,
    material_id uuid not null,
    quantity_on_hand numeric(20,6) not null default 0 check (quantity_on_hand >= 0),
    quantity_reserved numeric(20,6) not null default 0 check (quantity_reserved >= 0),
    quantity_available numeric(20,6) generated always as (
        quantity_on_hand - quantity_reserved
    ) stored,
    average_unit_cost numeric(20,4) check (average_unit_cost is null or average_unit_cost >= 0),
    currency_code text,
    last_movement_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id)
        references construction.projects(organization_id, id) on delete restrict,
    foreign key (organization_id, project_scope_id, inventory_location_id)
        references construction.inventory_locations(organization_id, project_scope_id, id) on delete restrict,
    foreign key (organization_id, material_id)
        references construction.material_items(organization_id, id) on delete restrict,
    unique (organization_id, project_scope_id, inventory_location_id, material_id),
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id),
    check (quantity_reserved <= quantity_on_hand),
    check ((average_unit_cost is null) = (currency_code is null)),
    check (currency_code is null or currency_code ~ '^[A-Z]{3}$')
);

create table construction.material_inventory_movements (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    inventory_location_id uuid not null,
    material_id uuid not null,
    direction text not null check (direction in ('in','out')),
    movement_type text not null check (movement_type in (
        'receipt','issue','transfer','adjustment','return'
    )),
    quantity numeric(20,6) not null check (quantity > 0),
    unit_cost numeric(20,4) check (unit_cost is null or unit_cost >= 0),
    currency_code text,
    occurred_at timestamptz not null,
    occurred_by uuid references auth.users(id) on delete set null,
    material_receipt_id uuid,
    purchase_order_item_id uuid,
    transfer_group_id uuid,
    external_reference text,
    notes text,
    created_at timestamptz not null default now(),
    foreign key (organization_id, project_id)
        references construction.projects(organization_id, id) on delete restrict,
    foreign key (organization_id, project_scope_id, inventory_location_id)
        references construction.inventory_locations(organization_id, project_scope_id, id) on delete restrict,
    foreign key (organization_id, material_id)
        references construction.material_items(organization_id, id) on delete restrict,
    foreign key (organization_id, project_id, material_receipt_id)
        references construction.material_receipts(
            organization_id, project_id, id
        ) on delete restrict,
    foreign key (organization_id, project_id, purchase_order_item_id)
        references construction.purchase_order_items(
            organization_id, project_id, id
        ) on delete restrict,
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id),
    check ((unit_cost is null) = (currency_code is null)),
    check (currency_code is null or currency_code ~ '^[A-Z]{3}$'),
    check (movement_type <> 'transfer' or transfer_group_id is not null),
    check (movement_type <> 'receipt' or (direction = 'in' and material_receipt_id is not null)),
    check (movement_type <> 'issue' or direction = 'out'),
    check (material_receipt_id is null or project_id is not null),
    check (purchase_order_item_id is null or project_id is not null)
);

alter table construction.purchase_order_items
    add column material_id uuid,
    add constraint purchase_order_items_material_tenant_fk
        foreign key (organization_id, material_id)
        references construction.material_items(organization_id, id) on delete restrict;

alter table construction.material_receipts
    add column material_id uuid,
    add column inventory_location_id uuid,
    add constraint material_receipts_material_tenant_fk
        foreign key (organization_id, material_id)
        references construction.material_items(organization_id, id) on delete restrict,
    add constraint material_receipts_location_scope_fk
        foreign key (organization_id, project_id, inventory_location_id)
        references construction.inventory_locations(organization_id, project_scope_id, id) on delete restrict;

-- A receipt or movement may only name the exact material ordered for the same
-- project.  Nullable retrofit columns preserve compatibility for pre-redesign
-- rows, while any new trace link is independently tenant/project/material safe.
alter table construction.purchase_order_items
    alter column quantity type numeric(20,6),
    alter column received_quantity type numeric(20,6),
    add constraint purchase_order_items_org_project_material_key
        unique (organization_id, project_id, id, material_id),
    add constraint purchase_order_items_received_within_ordered_check
        check (received_quantity <= quantity),
    add constraint purchase_order_items_line_amount_nonnegative_check
        check (line_amount >= 0);

alter table construction.purchase_orders
    add constraint purchase_orders_amounts_nonnegative_check
        check (subtotal >= 0 and tax_amount >= 0 and total_amount >= 0),
    add constraint purchase_orders_required_date_check
        check (required_date is null or required_date >= order_date),
    add constraint purchase_orders_currency_code_check
        check (currency_code ~ '^[A-Z]{3}$');

alter table construction.material_receipts
    alter column quantity_received type numeric(20,6),
    alter column quantity_accepted type numeric(20,6),
    alter column quantity_rejected type numeric(20,6),
    add constraint material_receipts_org_project_material_key
        unique (organization_id, project_id, id, material_id),
    add constraint material_receipts_ordered_material_fk
        foreign key (organization_id, project_id, purchase_order_item_id, material_id)
        references construction.purchase_order_items(
            organization_id, project_id, id, material_id
        ) on delete restrict;

alter table construction.material_inventory_movements
    add constraint material_inventory_movements_receipt_material_fk
        foreign key (organization_id, project_id, material_receipt_id, material_id)
        references construction.material_receipts(
            organization_id, project_id, id, material_id
        ) on delete restrict,
    add constraint material_inventory_movements_order_material_fk
        foreign key (organization_id, project_id, purchase_order_item_id, material_id)
        references construction.purchase_order_items(
            organization_id, project_id, id, material_id
        ) on delete restrict;

alter table construction.equipment
    add constraint equipment_purchase_cost_nonnegative_check
        check (purchase_cost is null or purchase_cost >= 0),
    add constraint equipment_current_meter_nonnegative_check
        check (current_meter is null or current_meter >= 0),
    add constraint equipment_next_service_meter_nonnegative_check
        check (next_service_meter is null or next_service_meter >= 0),
    add constraint equipment_currency_code_check
        check (currency_code is null or currency_code ~ '^[A-Z]{3}$');

alter table construction.equipment_assignments
    add constraint equipment_assignments_hourly_rate_nonnegative_check
        check (hourly_rate is null or hourly_rate >= 0),
    add constraint equipment_assignments_meter_order_check
        check (start_meter is null or end_meter is null or end_meter >= start_meter),
    add constraint equipment_assignments_currency_code_check
        check (currency_code is null or currency_code ~ '^[A-Z]{3}$');

alter table construction.equipment_maintenance
    add constraint equipment_maintenance_meter_nonnegative_check
        check (meter_reading is null or meter_reading >= 0),
    add constraint equipment_maintenance_next_meter_nonnegative_check
        check (next_service_meter is null or next_service_meter >= 0),
    add constraint equipment_maintenance_costs_nonnegative_check
        check (parts_cost >= 0 and labor_cost >= 0),
    add constraint equipment_maintenance_currency_code_check
        check (currency_code is null or currency_code ~ '^[A-Z]{3}$'),
    add constraint equipment_maintenance_time_order_check
        check (completed_at is null or started_at is null or completed_at >= started_at);

create index inventory_locations_project_fk_idx
    on construction.inventory_locations (organization_id, project_id);
create index material_inventory_balances_project_fk_idx
    on construction.material_inventory_balances (organization_id, project_id);
create index material_inventory_balances_material_fk_idx
    on construction.material_inventory_balances (organization_id, material_id);
create index material_inventory_balances_stock_idx
    on construction.material_inventory_balances (
        organization_id, project_scope_id, material_id, quantity_available
    );
create index material_inventory_movements_project_fk_idx
    on construction.material_inventory_movements (organization_id, project_id);
create index material_inventory_movements_location_fk_idx
    on construction.material_inventory_movements (
        organization_id, project_scope_id, inventory_location_id
    );
create index material_inventory_movements_material_fk_idx
    on construction.material_inventory_movements (organization_id, material_id);
create index material_inventory_movements_receipt_fk_idx
    on construction.material_inventory_movements (
        organization_id, project_id, material_receipt_id, material_id
    );
create index material_inventory_movements_po_item_fk_idx
    on construction.material_inventory_movements (
        organization_id, project_id, purchase_order_item_id, material_id
    );
create index material_inventory_movements_occurred_by_fk_idx
    on construction.material_inventory_movements (occurred_by);
create index material_inventory_movements_trace_idx
    on construction.material_inventory_movements (
        organization_id, project_scope_id, material_id, occurred_at desc
    );
create index material_inventory_movements_transfer_idx
    on construction.material_inventory_movements (organization_id, transfer_group_id)
    where transfer_group_id is not null;
create index purchase_order_items_material_fk_idx
    on construction.purchase_order_items (organization_id, material_id);
create index material_receipts_material_fk_idx
    on construction.material_receipts (organization_id, material_id);
create index material_receipts_location_fk_idx
    on construction.material_receipts (organization_id, project_id, inventory_location_id);
create index material_receipts_ordered_material_fk_idx
    on construction.material_receipts (
        organization_id, project_id, purchase_order_item_id, material_id
    );
create index material_items_created_by_fk_idx
    on construction.material_items (created_by);
create index material_items_updated_by_fk_idx
    on construction.material_items (updated_by);
create index inventory_locations_created_by_fk_idx
    on construction.inventory_locations (created_by);
create index inventory_locations_updated_by_fk_idx
    on construction.inventory_locations (updated_by);

create trigger material_items_touch_updated_at
before update on construction.material_items
for each row execute function construction_private.touch_updated_at();
create trigger inventory_locations_touch_updated_at
before update on construction.inventory_locations
for each row execute function construction_private.touch_updated_at();
create trigger material_inventory_balances_touch_updated_at
before update on construction.material_inventory_balances
for each row execute function construction_private.touch_updated_at();

create or replace function construction_private.reject_material_movement_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    raise exception 'material inventory movements are append-only'
        using errcode = '55000';
end;
$$;

create trigger material_inventory_movements_append_only
before update or delete on construction.material_inventory_movements
for each row execute function construction_private.reject_material_movement_mutation();

revoke execute on function construction_private.reject_material_movement_mutation()
from public, anon, authenticated, service_role;

alter table construction.material_items enable row level security;
alter table construction.inventory_locations enable row level security;
alter table construction.material_inventory_balances enable row level security;
alter table construction.material_inventory_movements enable row level security;

create policy tenant_read on construction.material_items
for select to authenticated
using ((select auth.uid()) is not null
       and (select construction_private.is_org_member(organization_id)));
create policy tenant_read on construction.inventory_locations
for select to authenticated
using ((select auth.uid()) is not null
       and (select construction_private.can_read_project(organization_id, project_id)));
create policy tenant_read on construction.material_inventory_balances
for select to authenticated
using ((select auth.uid()) is not null
       and (select construction_private.can_read_project(organization_id, project_id)));
create policy tenant_read on construction.material_inventory_movements
for select to authenticated
using ((select auth.uid()) is not null
       and (select construction_private.can_read_project(organization_id, project_id)));

revoke all on construction.material_items,
    construction.inventory_locations,
    construction.material_inventory_balances,
    construction.material_inventory_movements
from public, anon, authenticated, service_role;
grant select on construction.material_items,
    construction.inventory_locations,
    construction.material_inventory_balances,
    construction.material_inventory_movements
to authenticated;

commit;
