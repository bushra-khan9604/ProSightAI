import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

/** Accessible, theme-aware selector shared across application workspaces. */
export default function SmartSelect({ label, value, options, onChange, icon: Icon, className="", compact=false, disabled=false }) {
  const [open,setOpen]=useState(false),[activeIndex,setActiveIndex]=useState(0);
  const rootRef=useRef(null),triggerRef=useRef(null),menuId=useId();
  const selectedIndex=Math.max(0,options.findIndex(option=>option.value===value));
  const selected=options[selectedIndex]||options[0];

  useEffect(()=>{
    if(!open)return;
    const closeOutside=event=>{if(rootRef.current&&!rootRef.current.contains(event.target))setOpen(false)};
    const closeEscape=event=>{if(event.key==="Escape"){setOpen(false);triggerRef.current?.focus()}};
    document.addEventListener("pointerdown",closeOutside,true);document.addEventListener("keydown",closeEscape);
    return()=>{document.removeEventListener("pointerdown",closeOutside,true);document.removeEventListener("keydown",closeEscape)};
  },[open]);

  function choose(option){onChange(option.value);setOpen(false);triggerRef.current?.focus()}
  function onKeyDown(event){
    if(["ArrowDown","ArrowUp","Home","End","Enter"," ","Escape"].includes(event.key))event.preventDefault();
    if(event.key==="Escape"){setOpen(false);return}
    if(event.key==="Enter"||event.key===" "){
      if(open&&options[activeIndex])choose(options[activeIndex]);else {setActiveIndex(selectedIndex);setOpen(true);}
      return;
    }
    if(event.key==="Home"){setOpen(true);setActiveIndex(0);return}
    if(event.key==="End"){setOpen(true);setActiveIndex(Math.max(0,options.length-1));return}
    if(event.key==="ArrowDown"&&options.length){setOpen(true);setActiveIndex(index=>(index+1)%options.length)}
    if(event.key==="ArrowUp"&&options.length){setOpen(true);setActiveIndex(index=>(index-1+options.length)%options.length)}
  }

  return <div className={`smart-select ${className} ${compact?"compact":""}`} ref={rootRef}>
    {label&&!compact&&<span className="smart-select-label">{label}</span>}
    <button type="button" className="smart-select-trigger" ref={triggerRef} disabled={disabled}
      role="combobox" aria-label={label||"Select an option"} aria-haspopup="listbox" aria-expanded={open}
      aria-controls={open?menuId:undefined} aria-activedescendant={open?`${menuId}-option-${activeIndex}`:undefined}
      onClick={()=>{if(!open)setActiveIndex(selectedIndex);setOpen(current=>!current)}} onKeyDown={onKeyDown}>
      {Icon&&<Icon size={17}/>}<span className="smart-select-value"><b>{selected?.label}</b>{selected?.description&&<small>{selected.description}</small>}</span>
      <ChevronDown className="select-chevron" size={16}/>
    </button>
    {open&&<div className="smart-select-menu" id={menuId} role="listbox" aria-label={label||"Options"}>
      {options.map((option,index)=><button type="button" role="option" tabIndex={-1} aria-selected={option.value===value}
        id={`${menuId}-option-${index}`} className={`${option.value===value?"selected":""} ${activeIndex===index?"active":""}`}
        key={option.value||"all"} onMouseEnter={()=>setActiveIndex(index)} onClick={()=>choose(option)}>
        <span><b>{option.label}</b>{option.description&&<small>{option.description}</small>}</span>{option.value===value&&<Check size={15}/>}
      </button>)}
    </div>}
  </div>;
}
