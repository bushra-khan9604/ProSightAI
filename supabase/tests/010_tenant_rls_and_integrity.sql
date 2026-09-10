-- Destructive-looking test data is confined to this transaction and rolled back.
-- Run only against a disposable local Supabase database.

begin;

insert into auth.users (
    instance_id, id, aud, role, email, encrypted_password,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) values
    ('00000000-0000-0000-0000-000000000000','11111111-1111-1111-1111-111111111111','authenticated','authenticated','owner-a@example.test','', '{}'::jsonb,'{}'::jsonb,now(),now()),
    ('00000000-0000-0000-0000-000000000000','22222222-2222-2222-2222-222222222222','authenticated','authenticated','viewer-a@example.test','', '{}'::jsonb,'{}'::jsonb,now(),now()),
    ('00000000-0000-0000-0000-000000000000','33333333-3333-3333-3333-333333333333','authenticated','authenticated','project-a@example.test','', '{}'::jsonb,'{}'::jsonb,now(),now()),
    ('00000000-0000-0000-0000-000000000000','44444444-4444-4444-4444-444444444444','authenticated','authenticated','owner-b@example.test','', '{}'::jsonb,'{}'::jsonb,now(),now()),
    ('00000000-0000-0000-0000-000000000000','55555555-5555-5555-5555-555555555555','authenticated','authenticated','manager-a@example.test','', '{}'::jsonb,'{}'::jsonb,now(),now());

insert into construction.organizations (id, code, legal_name) values
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','TEST-ORG-A','Test Organization A'),
    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','TEST-ORG-B','Test Organization B');

insert into construction.organization_members
    (id, organization_id, user_id, role, is_active)
values
    ('a1111111-1111-1111-1111-111111111111','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','11111111-1111-1111-1111-111111111111','owner',true),
    ('a2222222-2222-2222-2222-222222222222','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','22222222-2222-2222-2222-222222222222','viewer',true),
    ('a3333333-3333-3333-3333-333333333333','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','33333333-3333-3333-3333-333333333333','member',true),
    ('a5555555-5555-5555-5555-555555555555','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','55555555-5555-5555-5555-555555555555','manager',true),
    ('b4444444-4444-4444-4444-444444444444','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','44444444-4444-4444-4444-444444444444','owner',true);

insert into construction.projects
    (id, organization_id, code, name, access_mode)
values
    ('aaaaaaaa-0000-0000-0000-000000000001','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','A-RESTRICTED','Restricted A','restricted'),
    ('aaaaaaaa-0000-0000-0000-000000000002','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','A-OPEN','Organization A','organization'),
    ('bbbbbbbb-0000-0000-0000-000000000001','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','B-OPEN','Organization B','organization');

do $reserved_project_scope$
declare rejected boolean := false;
begin
    begin
        insert into construction.projects (id, organization_id, code, name)
        values (
            '00000000-0000-0000-0000-000000000000',
            'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','ZERO-SCOPE','Must fail'
        );
    exception when check_violation then
        rejected := true;
    end;
    if not rejected then
        raise exception 'reserved null-scope UUID was accepted as a real project';
    end if;
end
$reserved_project_scope$;

insert into construction.project_members
    (id, organization_id, project_id, user_id, role, is_active)
values (
    'aaaaaaaa-3333-3333-3333-333333333333',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'aaaaaaaa-0000-0000-0000-000000000001',
    '33333333-3333-3333-3333-333333333333',
    'member', true
);

do $cross_organization_fk$
declare rejected boolean := false;
begin
    begin
        insert into construction.project_members
            (organization_id, project_id, user_id, role)
        values (
            'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
            'bbbbbbbb-0000-0000-0000-000000000001',
            '22222222-2222-2222-2222-222222222222',
            'member'
        );
    exception when foreign_key_violation then
        rejected := true;
    end;
    if not rejected then
        raise exception 'cross-organization project membership was not rejected';
    end if;
end
$cross_organization_fk$;

insert into construction.wbs_items
    (id, organization_id, project_id, code, name)
values (
    'aaaaaaaa-1000-0000-0000-000000000001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'aaaaaaaa-0000-0000-0000-000000000001',
    'WBS-1', 'Restricted WBS'
);

do $cross_project_fk$
declare rejected boolean := false;
begin
    begin
        insert into construction.activities (
            organization_id, project_id, wbs_item_id, activity_code, name
        ) values (
            'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
            'aaaaaaaa-0000-0000-0000-000000000002',
            'aaaaaaaa-1000-0000-0000-000000000001',
            'ACT-X', 'Hostile cross-project activity'
        );
    exception when foreign_key_violation then
        rejected := true;
    end;
    if not rejected then
        raise exception 'cross-project parent reference was not rejected';
    end if;
end
$cross_project_fk$;

insert into construction.business_units (id, organization_id, code, name)
values (
    'aaaaaaaa-2000-0000-0000-000000000001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','UNIT-SET-NULL','Nullable unit'
);
insert into construction.employees (
    id, organization_id, business_unit_id, employee_number, first_name
) values (
    'aaaaaaaa-2100-0000-0000-000000000001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'aaaaaaaa-2000-0000-0000-000000000001','EMP-SET-NULL','Tenant Safe'
);
delete from construction.business_units
where id = 'aaaaaaaa-2000-0000-0000-000000000001';

do $column_specific_set_null_behavior$
begin
    if not exists (
        select 1 from construction.employees
        where id = 'aaaaaaaa-2100-0000-0000-000000000001'
          and organization_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
          and business_unit_id is null
    ) then
        raise exception 'column-specific SET NULL did not preserve organization_id';
    end if;
end
$column_specific_set_null_behavior$;

insert into construction.material_items (
    id, organization_id, material_code, name, unit_code
) values
    ('aaaaaaaa-3000-0000-0000-000000000001','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','MAT-A','Material A','EA'),
    ('bbbbbbbb-3000-0000-0000-000000000001','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','MAT-B','Material B','EA');
insert into construction.inventory_locations (
    id, organization_id, project_id, location_code, name
) values (
    'aaaaaaaa-3100-0000-0000-000000000001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'aaaaaaaa-0000-0000-0000-000000000001','STORE-A','Restricted store'
);

do $material_scope_foreign_keys$
declare rejected boolean := false;
begin
    begin
        insert into construction.material_inventory_balances (
            organization_id, project_id, inventory_location_id, material_id,
            quantity_on_hand, quantity_reserved
        ) values (
            'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
            'aaaaaaaa-0000-0000-0000-000000000002',
            'aaaaaaaa-3100-0000-0000-000000000001',
            'aaaaaaaa-3000-0000-0000-000000000001',10.000001,0
        );
    exception when foreign_key_violation then
        rejected := true;
    end;
    if not rejected then
        raise exception 'inventory balance accepted a cross-project location';
    end if;

    rejected := false;
    begin
        insert into construction.material_inventory_balances (
            organization_id, project_id, inventory_location_id, material_id,
            quantity_on_hand, quantity_reserved
        ) values (
            'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
            'aaaaaaaa-0000-0000-0000-000000000001',
            'aaaaaaaa-3100-0000-0000-000000000001',
            'bbbbbbbb-3000-0000-0000-000000000001',10.000001,0
        );
    exception when foreign_key_violation then
        rejected := true;
    end;
    if not rejected then
        raise exception 'inventory balance accepted a cross-organization material';
    end if;
end
$material_scope_foreign_keys$;

insert into construction.material_inventory_movements (
    id, organization_id, project_id, inventory_location_id, material_id,
    direction, movement_type, quantity, occurred_at
) values (
    'aaaaaaaa-3200-0000-0000-000000000001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'aaaaaaaa-0000-0000-0000-000000000001',
    'aaaaaaaa-3100-0000-0000-000000000001',
    'aaaaaaaa-3000-0000-0000-000000000001',
    'in','adjustment',1.000001,now()
);

do $movement_append_only$
declare rejected boolean := false;
begin
    begin
        update construction.material_inventory_movements
        set quantity = 2.000001
        where id = 'aaaaaaaa-3200-0000-0000-000000000001';
    exception when object_not_in_prerequisite_state then
        rejected := true;
    end;
    if not rejected then
        raise exception 'material inventory movement was mutable';
    end if;
end
$movement_append_only$;

set local role authenticated;

select set_config('request.jwt.claim.sub','22222222-2222-2222-2222-222222222222',true);
do $viewer_scope$
begin
    if (select count(*) from construction.projects) <> 1 then
        raise exception 'ordinary organization viewer did not see exactly the organization-access project';
    end if;
    if exists (
        select 1 from construction.projects
        where id in (
            'aaaaaaaa-0000-0000-0000-000000000001',
            'bbbbbbbb-0000-0000-0000-000000000001'
        )
    ) then
        raise exception 'viewer crossed a restricted-project or organization boundary';
    end if;
end
$viewer_scope$;

select set_config('request.jwt.claim.sub','33333333-3333-3333-3333-333333333333',true);
do $project_member_scope$
begin
    if (select count(*) from construction.projects) <> 2 then
        raise exception 'active project member did not see open plus assigned restricted projects';
    end if;
    if exists (
        select 1 from construction.projects
        where organization_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
    ) then
        raise exception 'project membership granted cross-organization access';
    end if;
end
$project_member_scope$;

select set_config('request.jwt.claim.sub','11111111-1111-1111-1111-111111111111',true);
do $owner_scope$
begin
    if (select count(*) from construction.projects) <> 2 then
        raise exception 'organization owner did not see all projects in own organization';
    end if;
end
$owner_scope$;

select set_config('request.jwt.claim.sub','99999999-9999-9999-9999-999999999999',true);
do $nonmember_scope$
begin
    if exists (select 1 from construction.projects) then
        raise exception 'authenticated nonmember received tenant data';
    end if;
end
$nonmember_scope$;

reset role;
rollback;
