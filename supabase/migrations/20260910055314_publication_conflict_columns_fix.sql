-- The LEFT JOIN used to assemble INSERT columns also produces rows without a
-- matching conflict-key name. format('%I', null) is an error, so exclude those
-- rows from the conflict-column aggregate.
do $migration$
declare
    function_definition text;
    old_fragment text := $old$string_agg(format('%I', key_name), ', ' order by key_ordinality),$old$;
    new_fragment text := $new$string_agg(format('%I', key_name), ', ' order by key_ordinality)
                    filter (where key_name is not null),$new$;
begin
    select pg_catalog.pg_get_functiondef(
        'construction_private.publish_import_batch_internal(uuid,uuid,text)'::regprocedure
    ) into strict function_definition;

    if pg_catalog.strpos(function_definition, new_fragment) > 0 then
        return;
    end if;
    if pg_catalog.strpos(function_definition, old_fragment) = 0 then
        raise exception 'publisher conflict-column aggregate has an unexpected definition';
    end if;

    execute pg_catalog.replace(function_definition, old_fragment, new_fragment);
end
$migration$;
