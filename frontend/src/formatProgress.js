export function formatProgress(value,unit='%',signed=false){
  if(value==null||value===''||!Number.isFinite(Number(value)))return '—';
  const rounded=Number(Number(value).toFixed(2));
  return `${signed&&rounded>0?'+':''}${rounded.toFixed(2)}${unit}`;
}
