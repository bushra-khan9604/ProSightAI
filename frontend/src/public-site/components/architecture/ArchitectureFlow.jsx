import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Search, 
  Database, 
  FileText, 
  PenTool, 
  Camera, 
  TrendingUp,
  ArrowRight,
  Sparkles,
  ChevronRight
} from 'lucide-react';

// Ambient Background Blueprint Vector Wireframes
const BuildingBlueprintSVG = () => (
  <svg 
    className="absolute left-0 top-1/2 -translate-y-1/2 w-[320px] sm:w-[420px] lg:w-[520px] h-[640px] pointer-events-none opacity-15 text-slate-400 z-0"
    viewBox="0 0 400 600"
    fill="none"
    stroke="currentColor"
    strokeWidth="0.75"
  >
    <line x1="10" y1="580" x2="390" y2="580" strokeDasharray="4 4" />
    <line x1="40" y1="40" x2="40" y2="580" strokeWidth="1.2" />
    <line x1="120" y1="40" x2="120" y2="580" />
    <line x1="200" y1="40" x2="200" y2="580" />
    <line x1="280" y1="40" x2="280" y2="580" />
    <line x1="360" y1="40" x2="360" y2="580" strokeWidth="1.2" />
    {[80, 140, 200, 260, 320, 380, 440, 500, 560].map((y, i) => (
      <g key={i}>
        <line x1="40" y1={y} x2="360" y2={y} strokeWidth={i % 2 === 0 ? "1.2" : "0.75"} />
        {i % 2 === 0 && (
          <>
            <line x1="40" y1={y} x2="120" y2={y - 60} strokeDasharray="3 3" opacity="0.4" />
            <line x1="120" y1={y} x2="40" y2={y - 60} strokeDasharray="3 3" opacity="0.4" />
            <line x1="280" y1={y} x2="360" y2={y - 60} strokeDasharray="3 3" opacity="0.4" />
            <line x1="360" y1={y} x2="280" y2={y - 60} strokeDasharray="3 3" opacity="0.4" />
          </>
        )}
      </g>
    ))}
  </svg>
);

const CraneBlueprintSVG = () => (
  <svg 
    className="absolute right-0 top-1/2 -translate-y-1/2 w-[320px] sm:w-[420px] lg:w-[520px] h-[640px] pointer-events-none opacity-15 text-slate-400 z-0"
    viewBox="0 0 400 600"
    fill="none"
    stroke="currentColor"
    strokeWidth="0.75"
  >
    <line x1="300" y1="70" x2="300" y2="580" strokeWidth="1.2" />
    <line x1="330" y1="70" x2="330" y2="580" strokeWidth="1.2" />
    {[110, 150, 190, 230, 270, 310, 350, 390, 430, 470, 510, 550].map((y, i) => (
      <g key={i}>
        <line x1="300" y1={y} x2="330" y2={y} />
        <line x1="300" y1={y} x2="330" y2={y - 40} strokeDasharray="3 3" opacity="0.5" />
        <line x1="330" y1={y} x2="300" y2={y - 40} strokeDasharray="3 3" opacity="0.5" />
      </g>
    ))}
    <line x1="30" y1="90" x2="385" y2="90" strokeWidth="1.2" />
    <line x1="30" y1="105" x2="385" y2="105" />
    <polygon points="315,30 300,70 330,70" strokeWidth="1.2" />
    <line x1="120" y1="105" x2="120" y2="260" strokeDasharray="3 3" />
    <path d="M 115 260 L 125 260 L 120 275" strokeWidth="1.2" />
  </svg>
);

const SparkleStarIcon = ({ className = "w-5 h-5" }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
    <path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5L12 2Z" strokeLinejoin="round" />
  </svg>
);

export const ArchitectureFlow = () => {
  const [hoveredAgent, setHoveredAgent] = useState(null);
  
  // Element Refs for Dynamic Endpoints Calculation
  const containerRef = useRef(null);
  const orbRef = useRef(null);
  const ragCardRef = useRef(null);
  const dbCardRef = useRef(null);
  const projectCardRef = useRef(null);
  const writerCardRef = useRef(null);
  const visionCardRef = useRef(null);
  const insightCardRef = useRef(null);

  const [svgDimensions, setSvgDimensions] = useState({ w: 1000, h: 620, orbX: 500, orbY: 310, orbR: 136 });
  const [dynamicPaths, setDynamicPaths] = useState(null);

  // Recalculate physical connection endpoints based on actual DOM bounds
  const updateConnectorGeometry = useCallback(() => {
    if (!containerRef.current || !orbRef.current) return;
    const cRect = containerRef.current.getBoundingClientRect();
    const orbRect = orbRef.current.getBoundingClientRect();

    if (cRect.width === 0 || cRect.height === 0) return;

    const orbCenterX = orbRect.left + orbRect.width / 2 - cRect.left;
    const orbCenterY = orbRect.top + orbRect.height / 2 - cRect.top;
    const orbRadius = orbRect.width / 2;

    setSvgDimensions({
      w: cRect.width,
      h: cRect.height,
      orbX: orbCenterX,
      orbY: orbCenterY,
      orbR: orbRadius
    });

    const cardRefMap = {
      rag: ragCardRef,
      database: dbCardRef,
      project: projectCardRef,
      writer: writerCardRef,
      vision: visionCardRef,
      insight: insightCardRef
    };

    const calculated = {};

    Object.keys(cardRefMap).forEach((id) => {
      const cardEl = cardRefMap[id].current;
      if (!cardEl) return;
      const cardRect = cardEl.getBoundingClientRect();

      let targetX, targetY;

      // 1. RAG Agent (Top-Left): right edge of card
      if (id === 'rag') {
        targetX = (cardRect.right - cRect.left) - 2;
        targetY = (cardRect.top + cardRect.height / 2) - cRect.top;
      }
      // 2. Database Agent (Middle-Left): right edge of card
      else if (id === 'database') {
        targetX = (cardRect.right - cRect.left) - 2;
        targetY = (cardRect.top + cardRect.height / 2) - cRect.top;
      }
      // 3. Validation Agent (Bottom-Left): right edge of card
      else if (id === 'project') {
        targetX = (cardRect.right - cRect.left) - 2;
        targetY = (cardRect.top + cardRect.height / 2) - cRect.top;
      }
      // 4. Writer Agent (Top-Right): left edge of card
      else if (id === 'writer') {
        targetX = (cardRect.left - cRect.left) + 2;
        targetY = (cardRect.top + cardRect.height / 2) - cRect.top;
      }
      // 5. Vision Agent (Middle-Right): left edge of card
      else if (id === 'vision') {
        targetX = (cardRect.left - cRect.left) + 2;
        targetY = (cardRect.top + cardRect.height / 2) - cRect.top;
      }
      // 6. Analytics Agent (Bottom-Right): left edge of card
      else if (id === 'insight') {
        targetX = (cardRect.left - cRect.left) + 2;
        targetY = (cardRect.top + cardRect.height / 2) - cRect.top;
      }

      // Angle from center orb to target card connection point
      const angle = Math.atan2(targetY - orbCenterY, targetX - orbCenterX);
      const endX = orbCenterX + orbRadius * Math.cos(angle);
      const endY = orbCenterY + orbRadius * Math.sin(angle);

      // Smooth Bezier curve control points matching 3rd and 4th image
      let pathStr;
      if (id === 'database' || id === 'vision') {
        pathStr = `M ${endX.toFixed(1)} ${endY.toFixed(1)} L ${targetX.toFixed(1)} ${targetY.toFixed(1)}`;
      } else {
        const cp1X = endX + (targetX - endX) * 0.35;
        const cp1Y = endY + (targetY - endY) * 0.65;
        const cp2X = targetX - (targetX - endX) * 0.25;
        const cp2Y = targetY;
        pathStr = `M ${endX.toFixed(1)} ${endY.toFixed(1)} C ${cp1X.toFixed(1)} ${cp1Y.toFixed(1)}, ${cp2X.toFixed(1)} ${cp2Y.toFixed(1)}, ${targetX.toFixed(1)} ${targetY.toFixed(1)}`;
      }
      
      const midX = endX + (targetX - endX) * 0.5;
      const midY = endY + (targetY - endY) * 0.5;

      calculated[id] = {
        path: pathStr,
        startDot: { x: targetX, y: targetY },
        midDot: { x: midX, y: midY },
        endDot: { x: endX, y: endY }
      };
    });

    setDynamicPaths(calculated);
  }, []);

  useEffect(() => {
    updateConnectorGeometry();
    const handleResize = () => updateConnectorGeometry();
    window.addEventListener('resize', handleResize);

    let observer;
    if (typeof ResizeObserver !== 'undefined' && containerRef.current) {
      observer = new ResizeObserver(handleResize);
      observer.observe(containerRef.current);
    }

    return () => {
      window.removeEventListener('resize', handleResize);
      if (observer) observer.disconnect();
    };
  }, [updateConnectorGeometry]);

  // Static fallback connections mapping matching 3rd & 4th reference images
  const connections = [
    {
      id: 'rag',
      gradientId: 'grad-rag',
      strokeColor: '#a855f7',
      dotColor: '#c084fc',
      path: 'M 404 214 C 385 175, 365 130, 335 130',
      startDot: { x: 335, y: 130 },
      midDot: { x: 372, y: 172 },
      endDot: { x: 404, y: 214 },
      delay: 0
    },
    {
      id: 'database',
      gradientId: 'grad-db',
      strokeColor: '#06b6d4',
      dotColor: '#38bdf8',
      path: 'M 364 310 L 320 310',
      startDot: { x: 320, y: 310 },
      midDot: { x: 342, y: 310 },
      endDot: { x: 364, y: 310 },
      delay: 0.5
    },
    {
      id: 'project',
      gradientId: 'grad-project',
      strokeColor: '#f43f5e',
      dotColor: '#fb7185',
      path: 'M 404 406 C 385 445, 365 490, 350 490',
      startDot: { x: 350, y: 490 },
      midDot: { x: 372, y: 448 },
      endDot: { x: 404, y: 406 },
      delay: 1.0
    },
    {
      id: 'writer',
      gradientId: 'grad-writer',
      strokeColor: '#10b981',
      dotColor: '#34d399',
      path: 'M 596 214 C 615 175, 635 130, 665 130',
      startDot: { x: 665, y: 130 },
      midDot: { x: 628, y: 172 },
      endDot: { x: 596, y: 214 },
      delay: 1.5
    },
    {
      id: 'vision',
      gradientId: 'grad-vision',
      strokeColor: '#f59e0b',
      dotColor: '#fb923c',
      path: 'M 636 310 L 680 310',
      startDot: { x: 680, y: 310 },
      midDot: { x: 658, y: 310 },
      endDot: { x: 636, y: 310 },
      delay: 2.0
    },
    {
      id: 'insight',
      gradientId: 'grad-insight',
      strokeColor: '#6366f1',
      dotColor: '#a855f7',
      path: 'M 596 406 C 615 445, 635 490, 650 490',
      startDot: { x: 650, y: 490 },
      midDot: { x: 628, y: 448 },
      endDot: { x: 596, y: 406 },
      delay: 2.5
    }
  ];

  return (
    <section id="features" className="relative pt-18 sm:pt-22 pb-16 sm:pb-24 overflow-hidden bg-[#f8fafc]">
      {/* LAYER 1: Spatial Background & Atmosphere */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[850px] h-[850px] bg-gradient-to-r from-cyan-400/10 via-indigo-500/10 to-purple-500/10 blur-[170px] rounded-full pointer-events-none z-0" />
      <div className="absolute inset-0 bg-blueprint-grid opacity-15 pointer-events-none z-0" />
      
      <BuildingBlueprintSVG />
      <CraneBlueprintSVG />

      {/* LAYER 2: Floating Ambient Particles */}
      <div className="absolute inset-0 pointer-events-none z-0 overflow-hidden">
        {[
          { left: '15%', top: '25%', delay: 0 },
          { left: '82%', top: '20%', delay: 1 },
          { left: '22%', top: '75%', delay: 2 },
          { left: '78%', top: '80%', delay: 1.5 },
          { left: '50%', top: '15%', delay: 0.5 }
        ].map((p, idx) => (
          <motion.div
            key={idx}
            className="absolute w-1.5 h-1.5 rounded-full bg-cyan-500/40 blur-[1px]"
            style={{ left: p.left, top: p.top }}
            animate={{
              y: [0, -12, 0],
              opacity: [0.3, 0.8, 0.3],
              scale: [1, 1.2, 1]
            }}
            transition={{
              duration: 4,
              repeat: Infinity,
              ease: "easeInOut",
              delay: p.delay
            }}
          />
        ))}
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        
        {/* HEADER SECTION */}
        <motion.div 
          initial={{ opacity: 0, y: 15 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center max-w-4xl mx-auto mb-3 sm:mb-4"
        >
          {/* POWERED BY MULTI-AGENT AI Badge */}
          <div className="inline-flex items-center gap-2 px-3 py-1 mb-3 text-xs font-semibold tracking-wider uppercase rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-600">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-500 animate-pulse" />
            POWERED BY MULTI-AGENT AI
          </div>

          {/* Main Title - Single Line requirement for "One intelligent construction system." */}
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-extrabold text-slate-900 tracking-tight leading-[1.15] text-center">
            <span className="block mb-1">Six AI agents.</span>
            <span className="block text-slate-900 whitespace-nowrap">One intelligent construction system.</span>
          </h2>

          {/* Subtitle */}
          <p className="mt-3 text-sm sm:text-base md:text-lg text-slate-600 leading-relaxed font-normal max-w-2xl mx-auto">
            From searching project documents to querying data and generating executive insights, specialized AI agents work together to turn construction data into actionable intelligence.
          </p>
        </motion.div>

        {/* ARCHITECTURE NETWORK & ORCHESTRATION CONTAINER */}
        <div ref={containerRef} className="relative min-h-[560px] lg:min-h-[520px] flex flex-col justify-center mb-5 sm:mb-10">
          
          {/* LAYER 4: DESKTOP DYNAMIC SVG NEURAL NETWORK CONNECTIONS */}
          <svg 
            className="hidden lg:block absolute inset-0 w-full h-full pointer-events-none z-10" 
            viewBox={`0 0 ${svgDimensions.w} ${svgDimensions.h}`} 
            fill="none"
          >
            <defs>
              {/* 1. RAG Agent - Soft Purple/Violet */}
              <linearGradient id="grad-rag" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#c084fc" />
                <stop offset="100%" stopColor="#818cf8" />
              </linearGradient>

              {/* 2. Database Agent - Soft Cyan */}
              <linearGradient id="grad-db" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#38bdf8" />
                <stop offset="100%" stopColor="#06b6d4" />
              </linearGradient>

              {/* 3. Validation Agent - Coral Pink / Rose */}
              <linearGradient id="grad-project" x1="0%" y1="100%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#fb7185" />
                <stop offset="100%" stopColor="#f43f5e" />
              </linearGradient>

              {/* 4. Writer Agent - Mint / Teal */}
              <linearGradient id="grad-writer" x1="100%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#34d399" />
                <stop offset="100%" stopColor="#2dd4bf" />
              </linearGradient>

              {/* 5. Vision Agent - Amber / Orange */}
              <linearGradient id="grad-vision" x1="100%" y1="0%" x2="0%" y2="0%">
                <stop offset="0%" stopColor="#fb923c" />
                <stop offset="100%" stopColor="#f59e0b" />
              </linearGradient>

              {/* 6. Analytics Agent - Soft Purple / Indigo */}
              <linearGradient id="grad-insight" x1="100%" y1="100%" x2="0%" y2="0%">
                <stop offset="0%" stopColor="#a855f7" />
                <stop offset="100%" stopColor="#6366f1" />
              </linearGradient>
            </defs>

            {/* LAYER 3: CONCENTRIC ORBITAL RINGS */}
            <circle cx={svgDimensions.orbX} cy={svgDimensions.orbY} r={svgDimensions.orbR + 10} stroke="#cbd5e1" strokeWidth="1" strokeDasharray="3 5" opacity="0.3" />
            <motion.circle 
              cx={svgDimensions.orbX} cy={svgDimensions.orbY} r={svgDimensions.orbR + 45} 
              stroke="#94a3b8" strokeWidth="1" strokeDasharray="4 6" opacity="0.25"
              animate={{ rotate: 360 }}
              transition={{ duration: 90, repeat: Infinity, ease: "linear" }}
              style={{ transformOrigin: `${svgDimensions.orbX}px ${svgDimensions.orbY}px` }}
            />
            <motion.circle 
              cx={svgDimensions.orbX} cy={svgDimensions.orbY} r={svgDimensions.orbR + 85} 
              stroke="#cbd5e1" strokeWidth="0.8" strokeDasharray="3 7" opacity="0.2"
              animate={{ rotate: -360 }}
              transition={{ duration: 120, repeat: Infinity, ease: "linear" }}
              style={{ transformOrigin: `${svgDimensions.orbX}px ${svgDimensions.orbY}px` }}
            />
            <circle cx={svgDimensions.orbX} cy={svgDimensions.orbY} r={svgDimensions.orbR + 125} stroke="#e2e8f0" strokeWidth="0.8" strokeDasharray="5 8" opacity="0.15" />

            {/* SVG Connection Paths & Ray-of-Dots Data Streams */}
            {connections.map((c) => {
              const isHovered = hoveredAgent === c.id;
              const dyn = dynamicPaths && dynamicPaths[c.id];

              const pathD = dyn ? dyn.path : c.path;
              const startDot = dyn ? dyn.startDot : c.startDot;
              const midDot = dyn ? dyn.midDot : c.midDot;
              const endDot = dyn ? dyn.endDot : c.endDot;

              return (
                <g 
                  key={c.id} 
                  className="transition-opacity duration-300" 
                  opacity={1}
                >
                  {/* Elegant Curved Gradient Connector Path */}
                  <path 
                    d={pathD} 
                    stroke={`url(#${c.gradientId})`} 
                    strokeWidth={isHovered ? "3.2" : "2.2"} 
                    strokeLinecap="round" 
                    opacity={isHovered ? 0.95 : 0.8}
                    className="transition-all duration-300"
                  />

                  {/* Ray-of-Dots Continuous Animated Path Stream (Center -> Card) */}
                  <motion.path 
                    d={pathD} 
                    stroke={`url(#${c.gradientId})`} 
                    strokeWidth={isHovered ? 3.8 : 2.8} 
                    strokeDasharray={isHovered ? "4 8" : "3.5 9"} 
                    strokeLinecap="round"
                    animate={{ strokeDashoffset: [0, -24] }}
                    transition={{ 
                      duration: 1.6, 
                      repeat: Infinity, 
                      ease: "linear",
                      delay: c.delay 
                    }}
                    opacity={isHovered ? 1.0 : 0.85}
                    className="transition-opacity duration-300"
                  />

                  {/* Start Node Dot (Agent Card Connection Point) */}
                  <circle 
                    cx={startDot.x} 
                    cy={startDot.y} 
                    r={isHovered ? 6 : 4.5} 
                    fill={c.dotColor} 
                    opacity={0.9}
                    className="transition-all duration-300"
                  />

                  {/* Mid Node Dot (Orbital Intersection Point) */}
                  {midDot && (
                    <circle 
                      cx={midDot.x} 
                      cy={midDot.y} 
                      r={isHovered ? 5 : 4} 
                      fill={c.dotColor} 
                      opacity={0.85}
                      className="transition-all duration-300"
                    />
                  )}

                  {/* End Node Dot (Center Orb Connection Point) */}
                  <circle 
                    cx={endDot.x} 
                    cy={endDot.y} 
                    r={isHovered ? 6 : 4.5} 
                    fill={c.dotColor} 
                    opacity={0.9}
                    className="transition-all duration-300"
                  />

                  {/* Luminous Ray-Dots Travelling Outward (Center -> Agent Card) */}
                  {[0, 0.5].map((offset, pIdx) => (
                    <motion.circle 
                      key={pIdx}
                      r={isHovered ? 4 : 3} 
                      fill={c.dotColor}
                      animate={{
                        cx: [endDot.x, startDot.x],
                        cy: [endDot.y, startDot.y],
                        opacity: isHovered ? [0.3, 0.95, 0] : [0.2, 0.85, 0]
                      }}
                      transition={{ 
                        duration: 2.4, 
                        repeat: Infinity, 
                        ease: "linear",
                        delay: c.delay + offset * 2.4
                      }}
                    />
                  ))}
                </g>
              );
            })}
          </svg>

          {/* DESKTOP 3-COLUMN ORCHESTRATION COMPOSITION */}
          <div className="hidden lg:grid grid-cols-12 items-center gap-4 relative z-20 max-w-6xl mx-auto w-full">
            
            {/* LEFT CARDS COLUMN */}
            <div className="col-span-4 space-y-16 flex flex-col items-start pr-2">
              
              {/* CARD 1: RAG AGENT (Top Left) */}
              <motion.div 
                onMouseEnter={() => setHoveredAgent('rag')}
                onMouseLeave={() => setHoveredAgent(null)}
                whileHover={{ y: -3 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                className="relative flex items-center group cursor-pointer transition-all duration-300"
              >
                {/* 3D Holographic Platform & Illustration */}
                <div className="relative w-20 h-20 sm:w-24 sm:h-24 rounded-2xl bg-gradient-to-br from-slate-100 to-purple-50/80 border border-slate-200/90 shadow-xs flex items-center justify-center shrink-0 z-30 -mr-6 group-hover:shadow-sm transition-all duration-300">
                  <img 
                    src="/assets/rag-illustration.jpg" 
                    alt="RAG Agent" 
                    className="w-16 h-16 sm:w-20 sm:h-20 object-cover rounded-xl shadow-xs"
                  />
                </div>

                {/* Glassmorphism Card */}
                <div ref={ragCardRef} className="w-[300px] bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-2xl p-5 pl-8 shadow-[0_4px_20px_rgba(15,23,42,0.04)] group-hover:border-purple-300 group-hover:shadow-[0_8px_25px_rgba(15,23,42,0.08)] transition-all duration-300">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Search className="w-4 h-4 text-purple-600 stroke-[2.2]" />
                      <h3 className="text-xs font-extrabold text-slate-900 tracking-wider uppercase">
                        RAG AGENT
                      </h3>
                    </div>
                    <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-purple-600 group-hover:translate-x-0.5 transition-all" />
                  </div>
                  <p className="text-xs text-slate-500 leading-snug mt-1 font-normal">
                    Searches blueprints, RFIs, specs, and change orders using semantic embeddings.
                  </p>
                  <div className="mt-3.5 flex flex-wrap gap-1.5">
                    {['Drawings', 'RFIs', 'Specs'].map((tag) => (
                      <span key={tag} className="px-2.5 py-0.5 bg-[#f1f4f9] text-slate-600 border border-slate-200/60 rounded-full text-[11px] font-medium">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </motion.div>

              {/* CARD 2: DATABASE AGENT (Middle Left) */}
              <motion.div 
                onMouseEnter={() => setHoveredAgent('database')}
                onMouseLeave={() => setHoveredAgent(null)}
                whileHover={{ y: -3 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                className="relative flex items-center group -ml-6 cursor-pointer transition-all duration-300"
              >
                <div className="relative w-20 h-20 sm:w-24 sm:h-24 rounded-2xl bg-gradient-to-br from-slate-100 to-cyan-50/80 border border-slate-200/90 shadow-xs flex items-center justify-center shrink-0 z-30 -mr-6 group-hover:shadow-sm transition-all duration-300">
                  <img 
                    src="/assets/database-illustration.jpg" 
                    alt="Database Agent" 
                    className="w-16 h-16 sm:w-20 sm:h-20 object-cover rounded-xl shadow-xs"
                  />
                </div>
                <div ref={dbCardRef} className="w-[300px] bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-2xl p-5 pl-8 shadow-[0_4px_20px_rgba(15,23,42,0.04)] group-hover:border-cyan-300 group-hover:shadow-[0_8px_25px_rgba(15,23,42,0.08)] transition-all duration-300">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Database className="w-4 h-4 text-cyan-600 stroke-[2.2]" />
                      <h3 className="text-xs font-extrabold text-slate-900 tracking-wider uppercase">
                        DATABASE AGENT
                      </h3>
                    </div>
                    <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-cyan-600 group-hover:translate-x-0.5 transition-all" />
                  </div>
                  <p className="text-xs text-slate-500 leading-snug mt-1 font-normal">
                    Queries real-time SQL and Primavera databases for line-item variance.
                  </p>
                  <div className="mt-3.5 flex flex-wrap gap-1.5">
                    {['SQL', 'Primavera', 'Variance'].map((tag) => (
                      <span key={tag} className="px-2.5 py-0.5 bg-[#f1f4f9] text-slate-600 border border-slate-200/60 rounded-full text-[11px] font-medium">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </motion.div>

              {/* CARD 3: VALIDATION AGENT (Bottom Left) */}
              <motion.div 
                onMouseEnter={() => setHoveredAgent('project')}
                onMouseLeave={() => setHoveredAgent(null)}
                whileHover={{ y: -3 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                className="relative flex items-center group ml-14 cursor-pointer transition-all duration-300"
              >
                <div className="relative w-20 h-20 sm:w-24 sm:h-24 rounded-2xl bg-gradient-to-br from-slate-100 to-rose-50/80 border border-slate-200/90 shadow-xs flex items-center justify-center shrink-0 z-30 -mr-6 group-hover:shadow-sm transition-all duration-300">
                  <img 
                    src="/assets/project-illustration.jpg" 
                    alt="Validation Agent" 
                    className="w-16 h-16 sm:w-20 sm:h-20 object-cover rounded-xl shadow-xs"
                  />
                </div>
                <div ref={projectCardRef} className="w-[300px] bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-2xl p-5 pl-8 shadow-[0_4px_20px_rgba(15,23,42,0.04)] group-hover:border-rose-300 group-hover:shadow-[0_8px_25px_rgba(15,23,42,0.08)] transition-all duration-300">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-rose-600 stroke-[2.2]" />
                      <h3 className="text-xs font-extrabold text-slate-900 tracking-wider uppercase">
                        VALIDATION AGENT
                      </h3>
                    </div>
                    <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-rose-600 group-hover:translate-x-0.5 transition-all" />
                  </div>
                  <p className="text-xs text-slate-500 leading-snug mt-1 font-normal">
                    Detects conflicting specs between architectural and structural drawings.
                  </p>
                  <div className="mt-3.5 flex flex-wrap gap-1.5">
                    {['Conflicts', 'Architectural', 'Structural'].map((tag) => (
                      <span key={tag} className="px-2.5 py-0.5 bg-[#f1f4f9] text-slate-600 border border-slate-200/60 rounded-full text-[11px] font-medium">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </motion.div>

            </div>

            {/* LAYER 6: CENTRAL AI ORCHESTRATOR HUB (Reduced Circle Size) */}
            <div className="col-span-4 flex justify-center items-center py-4 relative z-30">
              <div 
                ref={orbRef}
                className="relative w-60 h-60 sm:w-68 sm:h-68 rounded-full flex flex-col items-center justify-center text-center p-5 sm:p-6 backdrop-blur-xl z-30 shadow-lg"
                style={{
                  background: 'radial-gradient(circle at 50% 40%, rgba(224, 242, 254, 0.98) 0%, rgba(238, 242, 255, 0.95) 50%, rgba(255, 255, 255, 0.98) 100%)',
                  boxShadow: '0 0 45px rgba(6, 182, 212, 0.18), 0 0 80px rgba(37, 99, 235, 0.12), inset 0 0 25px rgba(255, 255, 255, 0.95)',
                  border: '1.5px solid rgba(186, 230, 253, 0.9)'
                }}
              >
                {/* Static Inner Aura Ring */}
                <div className="absolute inset-2 rounded-full border border-cyan-400/30 pointer-events-none" />

                {/* 4-Point Star Sparkle Icon */}
                <div className="text-slate-800 mb-1">
                  <SparkleStarIcon className="w-5 h-5 stroke-[2.2] text-cyan-600" />
                </div>

                {/* Orb Titles */}
                <h3 className="text-sm sm:text-base font-extrabold tracking-wider text-slate-900 uppercase leading-tight">
                  <span className="block text-cyan-600">AI</span>
                  <span className="block text-slate-900">ORCHESTRATOR</span>
                </h3>

                {/* Orb Subtitle */}
                <p className="text-[10px] sm:text-[11px] text-slate-600 font-medium max-w-[160px] leading-tight mt-1 mb-2.5">
                  Multi-agent query routing & reasoning
                </p>

                {/* 3 Bullet Points */}
                <div className="space-y-0.5 text-left">
                  <div className="text-[10px] sm:text-[11px] font-semibold text-slate-700 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-500 shrink-0"></span>
                    Understands
                  </div>
                  <div className="text-[10px] sm:text-[11px] font-semibold text-slate-700 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0"></span>
                    Routes
                  </div>
                  <div className="text-[10px] sm:text-[11px] font-semibold text-slate-700 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 shrink-0"></span>
                    Delivers
                  </div>
                </div>
              </div>
            </div>

            {/* RIGHT CARDS COLUMN */}
            <div className="col-span-4 space-y-16 flex flex-col items-end pl-2">
              
              {/* CARD 4: WRITER AGENT (Top Right) */}
              <motion.div 
                onMouseEnter={() => setHoveredAgent('writer')}
                onMouseLeave={() => setHoveredAgent(null)}
                whileHover={{ y: -3 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                className="relative flex items-center group cursor-pointer transition-all duration-300"
              >
                <div ref={writerCardRef} className="w-[300px] bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-2xl p-5 pr-8 shadow-[0_4px_20px_rgba(15,23,42,0.04)] group-hover:border-teal-300 group-hover:shadow-[0_8px_25px_rgba(15,23,42,0.08)] transition-all duration-300">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <PenTool className="w-4 h-4 text-teal-600 stroke-[2.2]" />
                      <h3 className="text-xs font-extrabold text-slate-900 tracking-wider uppercase">
                        WRITER AGENT
                      </h3>
                    </div>
                    <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-teal-600 group-hover:translate-x-0.5 transition-all" />
                  </div>
                  <p className="text-xs text-slate-500 leading-snug mt-1 font-normal">
                    Drafts executive briefs, site reports, and owner updates with exact page references.
                  </p>
                  <div className="mt-3.5 flex flex-wrap gap-1.5">
                    {['Briefs', 'Reports', 'Page Refs'].map((tag) => (
                      <span key={tag} className="px-2.5 py-0.5 bg-[#f1f4f9] text-slate-600 border border-slate-200/60 rounded-full text-[11px] font-medium">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="relative w-20 h-20 sm:w-24 sm:h-24 rounded-2xl bg-gradient-to-br from-slate-100 to-teal-50/80 border border-slate-200/90 shadow-xs flex items-center justify-center shrink-0 z-30 -ml-6 group-hover:shadow-sm transition-all duration-300">
                  <img 
                    src="/assets/writer-illustration.jpg" 
                    alt="Writer Agent" 
                    className="w-16 h-16 sm:w-20 sm:h-20 object-cover rounded-xl shadow-xs"
                  />
                </div>
              </motion.div>

              {/* CARD 5: VISION AGENT (Middle Right) */}
              <motion.div 
                onMouseEnter={() => setHoveredAgent('vision')}
                onMouseLeave={() => setHoveredAgent(null)}
                whileHover={{ y: -3 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                className="relative flex items-center group -mr-6 cursor-pointer transition-all duration-300"
              >
                <div ref={visionCardRef} className="w-[300px] bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-2xl p-5 pr-8 shadow-[0_4px_20px_rgba(15,23,42,0.04)] group-hover:border-amber-300 group-hover:shadow-[0_8px_25px_rgba(15,23,42,0.08)] transition-all duration-300">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Camera className="w-4 h-4 text-amber-600 stroke-[2.2]" />
                      <h3 className="text-xs font-extrabold text-slate-900 tracking-wider uppercase">
                        VISION AGENT
                      </h3>
                    </div>
                    <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-amber-600 group-hover:translate-x-0.5 transition-all" />
                  </div>
                  <p className="text-xs text-slate-500 leading-snug mt-1 font-normal">
                    Understands drawings, 3D BIM models & site conditions.
                  </p>
                  <div className="mt-3.5 flex flex-wrap gap-1.5">
                    {['Plans', 'BIM', 'Photos'].map((tag) => (
                      <span key={tag} className="px-2.5 py-0.5 bg-[#f1f4f9] text-slate-600 border border-slate-200/60 rounded-full text-[11px] font-medium">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="relative w-20 h-20 sm:w-24 sm:h-24 rounded-2xl bg-gradient-to-br from-slate-100 to-amber-50/80 border border-slate-200/90 shadow-xs flex items-center justify-center shrink-0 z-30 -ml-6 group-hover:shadow-sm transition-all duration-300">
                  <img 
                    src="/assets/vision-illustration.jpg" 
                    alt="Vision Agent" 
                    className="w-16 h-16 sm:w-20 sm:h-20 object-cover rounded-xl shadow-xs"
                  />
                </div>
              </motion.div>

              {/* CARD 6: ANALYTICS AGENT (Bottom Right) */}
              <motion.div 
                onMouseEnter={() => setHoveredAgent('insight')}
                onMouseLeave={() => setHoveredAgent(null)}
                whileHover={{ y: -3 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                className="relative flex items-center group mr-14 cursor-pointer transition-all duration-300"
              >
                <div ref={insightCardRef} className="w-[300px] bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-2xl p-5 pr-8 shadow-[0_4px_20px_rgba(15,23,42,0.04)] group-hover:border-indigo-300 group-hover:shadow-[0_8px_25px_rgba(15,23,42,0.08)] transition-all duration-300">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-indigo-600 stroke-[2.2]" />
                      <h3 className="text-xs font-extrabold text-slate-900 tracking-wider uppercase">
                        ANALYTICS AGENT
                      </h3>
                    </div>
                    <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-indigo-600 group-hover:translate-x-0.5 transition-all" />
                  </div>
                  <p className="text-xs text-slate-500 leading-snug mt-1 font-normal">
                    Forecasts critical path schedule impact based on historic supply chain metrics.
                  </p>
                  <div className="mt-3.5 flex flex-wrap gap-1.5">
                    {['Critical Path', 'Schedule', 'Metrics'].map((tag) => (
                      <span key={tag} className="px-2.5 py-0.5 bg-[#f1f4f9] text-slate-600 border border-slate-200/60 rounded-full text-[11px] font-medium">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="relative w-20 h-20 sm:w-24 sm:h-24 rounded-2xl bg-gradient-to-br from-slate-100 to-indigo-50/80 border border-slate-200/90 shadow-xs flex items-center justify-center shrink-0 z-30 -ml-6 group-hover:shadow-sm transition-all duration-300">
                  <img 
                    src="/assets/insight-illustration.jpg" 
                    alt="Analytics Agent" 
                    className="w-16 h-16 sm:w-20 sm:h-20 object-cover rounded-xl shadow-xs"
                  />
                </div>
              </motion.div>

            </div>
          </div>

          {/* RESPONSIVE MOBILE / TABLET LAYOUT (< lg screens) */}
          <div className="lg:hidden flex flex-col items-center gap-8 relative z-10">
            {/* Center Orb for Mobile */}
            <div 
              className="w-56 h-56 rounded-full flex flex-col items-center justify-center text-center p-5 backdrop-blur-md shadow-lg"
              style={{
                background: 'radial-gradient(circle, rgba(224, 242, 254, 0.95) 0%, rgba(238, 242, 255, 0.90) 50%, rgba(255, 255, 255, 0.95) 100%)',
                boxShadow: '0 0 35px rgba(6, 182, 212, 0.18), 0 0 60px rgba(37, 99, 235, 0.12)',
                border: '1px solid rgba(186, 230, 253, 0.85)'
              }}
            >
              <div className="text-slate-800 mb-1">
                <SparkleStarIcon className="w-4.5 h-4.5 stroke-[2] text-cyan-600" />
              </div>
              <h3 className="text-sm font-extrabold tracking-wider uppercase leading-tight">
                <span className="block text-cyan-600">AI</span>
                <span className="block text-slate-900">ORCHESTRATOR</span>
              </h3>
              <p className="text-[10px] text-slate-600 font-medium max-w-[150px] leading-tight mt-1 mb-2">
                Multi-agent query routing & reasoning
              </p>
              <div className="space-y-0.5 text-left text-[10px] font-medium text-slate-700">
                <div className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-cyan-500"></span>Understands</div>
                <div className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>Routes</div>
                <div className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-indigo-500"></span>Delivers</div>
              </div>
            </div>

            {/* Mobile Cards Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 w-full max-w-2xl px-2">
              {/* RAG AGENT */}
              <div className="bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-2xl p-4.5 shadow-sm flex items-center gap-3">
                <img src="/assets/rag-illustration.jpg" alt="RAG" className="w-14 h-14 object-cover rounded-xl shrink-0" />
                <div>
                  <h3 className="text-xs font-extrabold text-slate-900 uppercase tracking-wider">RAG AGENT</h3>
                  <p className="text-[11px] text-slate-500 mt-0.5">Searches blueprints, RFIs, specs, and change orders using semantic embeddings.</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {['Drawings', 'RFIs', 'Specs'].map(t => (
                      <span key={t} className="px-2 py-0.5 bg-[#f1f4f9] text-slate-600 rounded-full text-[10px] font-medium">{t}</span>
                    ))}
                  </div>
                </div>
              </div>

              {/* WRITER AGENT */}
              <div className="bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-2xl p-4.5 shadow-sm flex items-center gap-3">
                <img src="/assets/writer-illustration.jpg" alt="Writer" className="w-14 h-14 object-cover rounded-xl shrink-0" />
                <div>
                  <h3 className="text-xs font-extrabold text-slate-900 uppercase tracking-wider">WRITER AGENT</h3>
                  <p className="text-[11px] text-slate-500 mt-0.5">Drafts executive briefs, site reports, and owner updates with exact page references.</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {['Briefs', 'Reports', 'Page Refs'].map(t => (
                      <span key={t} className="px-2 py-0.5 bg-[#f1f4f9] text-slate-600 rounded-full text-[10px] font-medium">{t}</span>
                    ))}
                  </div>
                </div>
              </div>

              {/* DATABASE AGENT */}
              <div className="bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-2xl p-4.5 shadow-sm flex items-center gap-3">
                <img src="/assets/database-illustration.jpg" alt="Database" className="w-14 h-14 object-cover rounded-xl shrink-0" />
                <div>
                  <h3 className="text-xs font-extrabold text-slate-900 uppercase tracking-wider">DATABASE AGENT</h3>
                  <p className="text-[11px] text-slate-500 mt-0.5">Queries real-time SQL and Primavera databases for line-item variance.</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {['SQL', 'Primavera', 'Variance'].map(t => (
                      <span key={t} className="px-2 py-0.5 bg-[#f1f4f9] text-slate-600 rounded-full text-[10px] font-medium">{t}</span>
                    ))}
                  </div>
                </div>
              </div>

              {/* VISION AGENT */}
              <div className="bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-2xl p-4.5 shadow-sm flex items-center gap-3">
                <img src="/assets/vision-illustration.jpg" alt="Vision" className="w-14 h-14 object-cover rounded-xl shrink-0" />
                <div>
                  <h3 className="text-xs font-extrabold text-slate-900 uppercase tracking-wider">VISION AGENT</h3>
                  <p className="text-[11px] text-slate-500 mt-0.5">Understands drawings, 3D BIM models & site conditions.</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {['Plans', 'BIM', 'Photos'].map(t => (
                      <span key={t} className="px-2 py-0.5 bg-[#f1f4f9] text-slate-600 rounded-full text-[10px] font-medium">{t}</span>
                    ))}
                  </div>
                </div>
              </div>

              {/* VALIDATION AGENT */}
              <div className="bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-2xl p-4.5 shadow-sm flex items-center gap-3">
                <img src="/assets/project-illustration.jpg" alt="Validation" className="w-14 h-14 object-cover rounded-xl shrink-0" />
                <div>
                  <h3 className="text-xs font-extrabold text-slate-900 uppercase tracking-wider">VALIDATION AGENT</h3>
                  <p className="text-[11px] text-slate-500 mt-0.5">Detects conflicting specs between architectural and structural drawings.</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {['Conflicts', 'Architectural', 'Structural'].map(t => (
                      <span key={t} className="px-2 py-0.5 bg-[#f1f4f9] text-slate-600 rounded-full text-[10px] font-medium">{t}</span>
                    ))}
                  </div>
                </div>
              </div>

              {/* ANALYTICS AGENT */}
              <div className="bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-2xl p-4.5 shadow-sm flex items-center gap-3">
                <img src="/assets/insight-illustration.jpg" alt="Analytics" className="w-14 h-14 object-cover rounded-xl shrink-0" />
                <div>
                  <h3 className="text-xs font-extrabold text-slate-900 uppercase tracking-wider">ANALYTICS AGENT</h3>
                  <p className="text-[11px] text-slate-500 mt-0.5">Forecasts critical path schedule impact based on historic supply chain metrics.</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {['Critical Path', 'Schedule', 'Metrics'].map(t => (
                      <span key={t} className="px-2 py-0.5 bg-[#f1f4f9] text-slate-600 rounded-full text-[10px] font-medium">{t}</span>
                    ))}
                  </div>
                </div>
              </div>

            </div>
          </div>

        </div>

      </div>
    </section>
  );
};

