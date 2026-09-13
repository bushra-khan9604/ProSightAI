export const ARCHITECTURE_NODES = [
  {
    id: 'pdf-upload',
    title: 'PDF DOCUMENT UPLOAD',
    subtitle: 'Extract text, blueprints & structural reports',
    icon: 'FileText',
    accentColor: 'from-red-500 to-rose-600',
    borderColor: 'border-red-500/40',
    glowColor: 'shadow-red-500/20',
    description: 'Ingests specs, submittals, and architectural PDF blueprints with high-precision OCR.'
  },
  {
    id: 'excel-import',
    title: 'EXCEL IMPORT',
    subtitle: 'Schedules, BOQs & cost breakdown structures',
    icon: 'FileSpreadsheet',
    accentColor: 'from-emerald-500 to-green-600',
    borderColor: 'border-emerald-500/40',
    glowColor: 'shadow-emerald-500/20',
    description: 'Parses complex multi-tab construction budgets, schedules, and bill of quantities automatically.'
  },
  {
    id: 'validate-approve',
    title: 'VALIDATE & APPROVE',
    subtitle: 'Data integrity & discrepancy check',
    icon: 'ShieldCheck',
    accentColor: 'from-cyan-500 to-blue-600',
    borderColor: 'border-cyan-500/40',
    glowColor: 'shadow-cyan-500/20',
    description: 'Cross-checks timeline dates, structural specs, and contractor submittals for inconsistencies.'
  },
  {
    id: 'update-db',
    title: 'UPDATE DATABASE',
    subtitle: 'Vectorized project memory store',
    icon: 'Database',
    accentColor: 'from-teal-400 to-emerald-500',
    borderColor: 'border-teal-500/40',
    glowColor: 'shadow-teal-500/20',
    description: 'Syncs structured site updates into a secure, version-controlled vector graph database.'
  },
  {
    id: 'rag-agent',
    title: 'RAG AGENT',
    subtitle: 'Semantic search across thousands of files',
    icon: 'Search',
    accentColor: 'from-purple-500 to-indigo-600',
    borderColor: 'border-purple-500/40',
    glowColor: 'shadow-purple-500/20',
    description: 'Retrieves contextual evidence from structural reports, RFIs, and daily inspection logs.'
  },
  {
    id: 'orchestrator',
    title: 'AI ORCHESTRATOR',
    subtitle: 'Multi-agent query routing & reasoning',
    icon: 'Cpu',
    accentColor: 'from-blue-500 to-cyan-500',
    borderColor: 'border-blue-500/40',
    glowColor: 'shadow-blue-500/20',
    description: 'Synthesizes specialized agents to answer complex multi-layered construction queries.'
  },
  {
    id: 'db-agent',
    title: 'DATABASE AGENT',
    subtitle: 'Direct SQL & vector memory querying',
    icon: 'HardDrive',
    accentColor: 'from-sky-400 to-blue-600',
    borderColor: 'border-sky-500/40',
    glowColor: 'shadow-sky-500/20',
    description: 'Executes rapid analytical queries over cost codes, schedule slippage, and material inventory.'
  },
  {
    id: 'writer-agent',
    title: 'WRITER AGENT',
    subtitle: 'Executive summaries & evidence reporting',
    icon: 'PenTool',
    accentColor: 'from-amber-400 to-yellow-500',
    borderColor: 'border-amber-500/40',
    glowColor: 'shadow-amber-500/20',
    description: 'Generates professional executive briefs, site variance reports, and client updates in seconds.'
  }
];

export const WORKFLOW_STEPS = [
  {
    step: '01',
    title: 'Upload Data',
    description: 'Drag & drop project specs, PDFs, Primavera XMLs, Excel BOQs, and site inspection logs into your secure vault.',
    icon: 'CloudUpload',
    badge: 'Step 1'
  },
  {
    step: '02',
    title: 'Validate & Process',
    description: 'ProSight AI ingests, cleans, vectorizes, and links document data to your master BIM and schedule model.',
    icon: 'CheckCircle2',
    badge: 'Step 2'
  },
  {
    step: '03',
    title: 'Ask Questions',
    description: 'Chat naturally with your project: ask about delays, cost variances, structural specs, or submittal statuses.',
    icon: 'MessageSquareText',
    badge: 'Step 3'
  },
  {
    step: '04',
    title: 'Get Insights',
    description: 'Receive instant, evidence-backed answers, cited documents, variance warnings, and automated action plans.',
    icon: 'Lightbulb',
    badge: 'Step 4'
  }
];

export const METRICS_DATA = [
  { value: 70, suffix: '%', label: 'Faster Decisions', subtext: 'Less time spent searching through scattered file folders and emails.' },
  { value: 99, suffix: '%', label: 'Data Validation Accuracy', subtext: 'Automated verification of cross-referencing submittals & BOQs.' },
  { value: 50, suffix: '%', label: 'Faster Project Reporting', subtext: 'Executive dashboards and variance briefs created automatically.' },
  { value: 100, suffix: '%', label: 'Evidence-Based Decisions', subtext: 'Every insight links directly back to your source blueprint or spec page.' }
];

export const DASHBOARD_DATA = {
  overallProgress: 68,
  scheduleAdherence: 82,
  budgetStatus: 74,
  openIssues: 12,
  criticalRisks: 3,
  documentsAnalyzed: 248,
  zones: [
    { name: 'Zone A - Substructure', progress: 94, status: 'On Track' },
    { name: 'Zone B - Structural Steel', progress: 78, status: 'On Track' },
    { name: 'Zone C - Facade & Glazing', progress: 54, status: 'Delayed 2 Days' },
    { name: 'Zone D - MEP Fit-out', progress: 42, status: 'On Track' }
  ],
  recentActivities: [
    { title: 'Steel structure inspection report updated', time: '12 mins ago', type: 'report' },
    { title: 'Material delivery ETA verified (Grade 60)', time: '45 mins ago', type: 'logistics' },
    { title: 'Site inspection completed for Beam B4', time: '2 hours ago', type: 'inspection' },
    { title: 'Submittal #108 approved by Structural Engineer', time: '4 hours ago', type: 'approval' }
  ]
};

