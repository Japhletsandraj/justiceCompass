import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  ArrowUpRight,
  BookOpen,
  BriefcaseBusiness,
  Check,
  ChevronRight,
  CircleAlert,
  Clock3,
  FileText,
  Gavel,
  LoaderCircle,
  Scale,
  Search,
  ShieldCheck,
  Sparkles,
  Sun,
  Moon,
} from 'lucide-react'
import './styles.css'
import './result-overrides.css'
import justiceLady from '../../assets/Justice_Lady.jpeg'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const starterCases = [
  'My landlord has refused to return my security deposit after I moved out. What can I do?',
  'I have been arrested and need to understand the grounds for seeking bail.',
]

const translations = {
  en: {
    name: 'English', workspace: 'Analysis workspace', eyebrow: 'LEGAL INTELLIGENCE, MADE CLEAR', hero: 'Find the path', heroEmphasis: 'forward.', heroText: 'Describe the facts of your situation. JusticeCompass maps relevant law, surfaces practical next steps, and shows where professional guidance matters most.',
    private: 'Private by design.', private2: 'Your question is used', private3: 'only for this assessment.', intake: 'CASE INTAKE', happened: 'What happened?', general: 'General information', placeholder: 'Tell us what happened, who was involved, and what you need to know...', examples: 'Try an example', analyse: 'Analyse case', analysing: 'Analysing...', report: 'ASSESSMENT REPORT', glance: 'Your case, at a glance', live: 'LIVE ANALYSIS', winRate: 'Historical signal', insufficient: 'Insufficient data', outcomes: 'comparable outcomes', cases: 'comparable cases', domain: 'Legal domain', underReview: 'Under review', primary: 'Primary classification', urgency: 'Urgency', reviewDates: 'Review dates', assessTiming: 'Assess timing', deadline: 'Deadline awareness', briefing: 'BRIEFING', meaning: 'What this may mean', references: 'REFERENCES', sources: 'Applicable laws', recommended: 'RECOMMENDED PATH', next: 'Next steps', prepare: 'PREPARE', evidence: 'Evidence to gather', historical: 'HISTORICAL SIGNAL', pastRate: 'Past-case win-rate', sourceNote: 'Statutes and constitutional provisions are the primary sources', disclaimerTitle: 'Important: this is not legal advice.', noSources: 'No applicable legal provisions returned.', noEvidence: 'No evidence checklist returned.', noSteps: 'No immediate steps returned.', ready: 'READY WHEN YOU ARE', readyTitle: 'Your analysis will appear here', readyText: 'Submit a case description to receive a structured view of relevant acts, confidence, and practical next steps.', language: 'Language', privateError: 'Please describe your situation in at least a few words.'
  },
  hi: {
    name: 'हिन्दी', workspace: 'विश्लेषण कार्यक्षेत्र', eyebrow: 'कानूनी जानकारी, सरल रूप में', hero: 'आगे बढ़ने का', heroEmphasis: 'रास्ता।', heroText: 'अपनी स्थिति के तथ्य लिखें। JusticeCompass संबंधित कानून और अगले व्यावहारिक कदम दिखाता है।',
    private: 'गोपनीयता का ध्यान रखा गया है।', private2: 'आपका प्रश्न केवल', private3: 'इस मूल्यांकन के लिए उपयोग होता है।', intake: 'मामले की जानकारी', happened: 'क्या हुआ?', general: 'सामान्य जानकारी', placeholder: 'बताएं कि क्या हुआ, कौन शामिल था और आप क्या जानना चाहते हैं...', examples: 'उदाहरण देखें', analyse: 'मामले का विश्लेषण करें', analysing: 'विश्लेषण हो रहा है...', report: 'मूल्यांकन रिपोर्ट', glance: 'आपका मामला एक नज़र में', live: 'लाइव विश्लेषण', winRate: 'अनुमानित मामले की सफलता दर', insufficient: 'पर्याप्त डेटा नहीं', outcomes: 'तुलनीय परिणाम', cases: 'तुलनीय मामले', domain: 'कानूनी क्षेत्र', underReview: 'समीक्षा में', primary: 'मुख्य वर्गीकरण', urgency: 'तात्कालिकता', reviewDates: 'तिथियां देखें', assessTiming: 'समय का आकलन करें', deadline: 'समय-सीमा की जानकारी', briefing: 'संक्षिप्त जानकारी', meaning: 'इसका क्या अर्थ हो सकता है', references: 'संदर्भ', sources: 'स्रोत', recommended: 'सुझाया गया मार्ग', next: 'अगले कदम', prepare: 'तैयारी', evidence: 'जमा किए जाने वाले प्रमाण', historical: 'ऐतिहासिक संकेत', pastRate: 'पिछले मामलों की सफलता दर', sourceNote: 'कानूनी प्रावधान और संदर्भ नीचे अलग दिखाए गए हैं', disclaimerTitle: 'महत्वपूर्ण: यह कानूनी सलाह नहीं है।', noSources: 'कोई स्रोत संदर्भ नहीं मिला।', noEvidence: 'कोई प्रमाण सूची नहीं मिली।', noSteps: 'कोई तत्काल कदम नहीं मिले।', ready: 'आप तैयार हैं', readyTitle: 'आपका विश्लेषण यहां दिखाई देगा', readyText: 'मामले का विवरण भेजें और संबंधित कानून, आकलन तथा अगले कदम देखें।', language: 'भाषा', privateError: 'कृपया अपनी स्थिति कुछ शब्दों में बताएं।'
  },
  ta: {
    name: 'தமிழ்', workspace: 'பகுப்பாய்வு பணியிடம்', eyebrow: 'சட்டத் தகவல், தெளிவாக', hero: 'முன்னே செல்லும்', heroEmphasis: 'வழி.', heroText: 'உங்கள் நிலைமையின் உண்மைகளை எழுதுங்கள். தொடர்புடைய சட்டத்தையும் அடுத்த நடைமுறை நடவடிக்கைகளையும் JusticeCompass காட்டும்.',
    private: 'தனியுரிமை பாதுகாக்கப்படுகிறது.', private2: 'உங்கள் கேள்வி', private3: 'இந்த மதிப்பீட்டிற்காக மட்டுமே பயன்படுத்தப்படும்.', intake: 'வழக்கு விவரங்கள்', happened: 'என்ன நடந்தது?', general: 'பொதுவான தகவல்', placeholder: 'என்ன நடந்தது, யார் தொடர்புடையவர்கள், நீங்கள் என்ன தெரிந்துகொள்ள விரும்புகிறீர்கள் என்பதை எழுதுங்கள்...', examples: 'உதாரணம்', analyse: 'வழக்கை பகுப்பாய்வு செய்', analysing: 'பகுப்பாய்வு செய்கிறது...', report: 'மதிப்பீட்டு அறிக்கை', glance: 'உங்கள் வழக்கு ஒரு பார்வையில்', live: 'நேரடி பகுப்பாய்வு', winRate: 'கணிக்கப்பட்ட வழக்கு வெற்றி விகிதம்', insufficient: 'போதுமான தரவு இல்லை', outcomes: 'ஒப்பிடத்தக்க முடிவுகள்', cases: 'ஒப்பிடத்தக்க வழக்குகள்', domain: 'சட்டப் பிரிவு', underReview: 'மதிப்பாய்வில்', primary: 'முதன்மை வகைப்பாடு', urgency: 'அவசரம்', reviewDates: 'தேதிகளை மதிப்பாய்வு செய்', assessTiming: 'நேரத்தை மதிப்பிடு', deadline: 'காலக்கெடு கவனம்', briefing: 'சுருக்கம்', meaning: 'இதன் பொருள் என்ன', references: 'ஆதாரங்கள்', sources: 'மூலங்கள்', recommended: 'பரிந்துரைக்கப்பட்ட பாதை', next: 'அடுத்த படிகள்', prepare: 'தயாரிப்பு', evidence: 'சேகரிக்க வேண்டிய ஆதாரங்கள்', historical: 'வரலாற்றுச் சுட்டு', pastRate: 'முந்தைய வழக்குகளின் வெற்றி விகிதம்', sourceNote: 'சட்ட விதிகளும் ஆதாரங்களும் கீழே தனித்தனியாக காட்டப்படும்', disclaimerTitle: 'முக்கியம்: இது சட்ட ஆலோசனை அல்ல.', noSources: 'ஆதாரங்கள் எதுவும் கிடைக்கவில்லை.', noEvidence: 'ஆதாரப் பட்டியல் எதுவும் கிடைக்கவில்லை.', noSteps: 'உடனடி நடவடிக்கைகள் எதுவும் கிடைக்கவில்லை.', ready: 'நீங்கள் தயாராக உள்ளீர்கள்', readyTitle: 'உங்கள் பகுப்பாய்வு இங்கே தோன்றும்', readyText: 'வழக்கு விவரத்தை அனுப்பி தொடர்புடைய சட்டம் மற்றும் அடுத்த படிகளைப் பெறுங்கள்.', language: 'மொழி', privateError: 'உங்கள் நிலைமையை சில வார்த்தைகளில் விவரிக்கவும்.'
  }
}

const emptyResult = {
  answer: '', confidence_score: 0, confidence_label: '', legal_domain: '', legal_issues: [], severity_assessment: '', potential_consequences: [],
  applicable_laws: [], immediate_steps: [], evidence_to_collect: [], possible_forums: [],
  deadlines: [], source_citations: [], disclaimer: '', historical_outcome_estimate: null, structured_answer: null,
}

function getActs(result) {
  const structuredActs = result.structured_answer?.applicable_law || []
  const contextActs = (result.context_items || []).flatMap((item) => {
    const metadata = item.metadata || {}
    const isLegalSource = ['statute', 'constitutional', 'crossreference'].includes(item.source_type)
      || metadata.act_abbrev || metadata.act_name || metadata.section_number || metadata.article_number
    if (!isLegalSource) return []
    const act = metadata.act_name || metadata.act_abbrev || metadata.act || metadata.statute_name
    const section = metadata.section_number || metadata.section || metadata.article_number
    const metadataLabel = act && section
      ? `${act} ${metadata.article_number ? 'Article' : 'Section'} ${section}`
      : act || item.source
    return [metadataLabel || item.source]
  })
  return [...new Set([...structuredActs, ...result.applicable_laws, ...contextActs].filter(Boolean))]
}

function getSources(result) {
  const structuredSources = result.structured_answer?.applicable_law || []
  return [...new Set([
    ...(result.source_citations || []),
    ...(result.applicable_laws || []),
    ...structuredSources,
    ...getActs(result),
  ].filter(Boolean))]
}

function getIssueSpecificSteps(result) {
  const steps = result.structured_answer?.next_steps || result.immediate_steps || []
  return steps
}

function getBriefingPoints(result) {
  const structured = result.structured_answer || {}
  const concern = structured.concern_assessment || result.concern_assessment || 'The facts indicate a legal concern that needs further review.'
  const severity = `Severity: ${result.severity_assessment || 'cannot be determined from the supplied facts.'}`
  const consequences = (result.potential_consequences || []).length
    ? `Potential consequences: ${result.potential_consequences.join(' ')}`
    : 'Potential consequences: the consequences depend on the missing facts, applicable provision, and whether any deadline has passed.'
  return [
    `Concern: ${concern} The available facts are enough to justify an initial legal review, but not enough to confirm liability, eligibility, or the correct remedy. More detail about the people involved, dates, location, and harm would make the assessment more useful.`,
    severity,
    consequences,
  ]
}

function App() {
  const [language, setLanguage] = useState('en')
  const [theme, setTheme] = useState(() => localStorage.getItem('justicecompass-theme') || 'night')
  const copy = translations[language]
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState(emptyResult)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [hasSearched, setHasSearched] = useState(false)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('justicecompass-theme', theme)
  }, [theme])

    async function handleSubmit(event) {
    event.preventDefault()
    if (question.trim().length < 8) {
      setError(copy.privateError)
      return
    }
    setLoading(true)
    setError('')

    try {
      const normalized = question.trim().toLowerCase()
      const caseType = /\bbail\b|bail application|anticipatory bail|regular bail/.test(normalized)
        ? 'bail'
        : null

      // One assessment request includes retrieval, legal analysis, and the
      // optional historical signal. Live judgment search is opt-in.
      const assessRes = await fetch(`${API_URL}/assess`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question: question.trim(),
      case_type: caseType,
      include_rag_answer: true,
      fetch_external_sources: false,
      fetch_full_judgments: false,
      max_full_judgments: 10,
    }),
      })

const assessPayload = await assessRes.json()

if (!assessRes.ok) throw new Error(assessPayload.detail || 'Assessment failed.')

setResult({
  ...emptyResult,
  ...assessPayload,
  historical_outcome_estimate: assessPayload.historical_outcome_estimate || null,
})
      setHasSearched(true)
    } catch (err) {
      setError(err.message || 'Unable to connect to JusticeCompass.')
    } finally {
      setLoading(false)
    }
  }
  const outcome = result.historical_outcome_estimate
  const hasHistoricalRate = outcome?.estimate !== null && outcome?.estimate !== undefined
  const winRate = hasHistoricalRate ? Math.round(outcome.estimate * 100) : null
  const briefingPoints = getBriefingPoints(result)

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark"><Scale size={17} /></span><span>Justice<span>Compass</span><small>LEGAL INTELLIGENCE</small></span></div>
        <nav className="desktop-nav" aria-label="Primary navigation"><a href="#how-it-works">How it works</a><a href="#domains">Domains</a><a href="#case-intake">Case intake</a><a href="#statutes">Statutes</a></nav>
        <div className="topbar-right"><span className="status-dot" /> <span className="workspace-label">{copy.workspace}</span><span className="divider" /><div className="theme-toggle" role="group" aria-label="Theme"><button className={theme === 'light' ? 'active' : ''} onClick={() => setTheme('light')} aria-label="Light mode" title="Light mode"><Sun size={14} /></button><button className={theme === 'night' ? 'active' : ''} onClick={() => setTheme('night')} aria-label="Night mode" title="Night mode"><Moon size={14} /></button></div><label className="language-switcher"><span>{copy.language}</span><select value={language} onChange={(event) => setLanguage(event.target.value)} aria-label={copy.language}>{Object.entries(translations).map(([code, item]) => <option value={code} key={code}>{item.name}</option>)}</select></label></div>
      </header>

      <main>
        <section className="hero-grid">
          <div className="hero-copy" id="how-it-works">
            <p className="eyebrow"><Sparkles size={14} /> {copy.eyebrow}</p>
            <h1>Turn your legal problem<br />into a <em>clearer path.</em></h1>
            <p className="hero-text">{copy.heroText}</p>
            <a className="hero-cta" href="#case-intake">Analyse my case <ChevronRight size={15} /></a>
            <div className="hero-proof"><span><ShieldCheck size={13} /> Evidence-aware pipeline</span><span><Scale size={13} /> Statutory mapping</span><span><BookOpen size={13} /> Privacy ensured</span></div>
          </div>
          <div className="hero-portrait"><div className="portrait-frame"><img src={justiceLady} alt="Justice Lady statue with scales" /><span className="portrait-stamp">JUSTICE<br />COMPASS</span><span className="portrait-caption">INDIAN LEGAL RESEARCH<br /><b>STATUTE FIRST</b></span></div></div>
        </section>

        <section className="foundation-band" id="domains"><div><span className="section-kicker">OUR FOUNDATION</span><h2>Law is complex.<br /><em>Your first step shouldn't be.</em></h2><p>JusticeCompass turns a difficult situation into a structured first brief: the relevant law, the practical route, the evidence to keep, and the questions a lawyer will need answered.</p></div><div className="method-list" id="how-it-works"><span>01 <b>Understand the situation</b><small>Translate everyday facts into legal issues and urgency.</small></span><span>02 <b>Map the applicable law</b><small>Prioritise current statutes and state-specific rules.</small></span><span>03 <b>Build a practical path</b><small>Surface steps, documents, deadlines, and forums.</small></span></div></section>

        <section className="search-panel" id="case-intake">
          <div className="panel-heading"><div><span className="section-kicker">{copy.intake}</span><h2>{copy.happened}</h2></div><span className="intake-badge"><ShieldCheck size={14} /> {copy.general}</span></div>
          <form onSubmit={handleSubmit}>
            <div className="textarea-wrap"><Search size={20} /><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={copy.placeholder} rows="4" /></div>
            <div className="form-footer"><div className="starter-row"><span>{copy.examples}</span>{starterCases.map((item) => <button type="button" className="example-button" key={item} onClick={() => setQuestion(item)}>{item.slice(0, 34)}... <ArrowUpRight size={13} /></button>)}</div><button className="submit-button" disabled={loading}>{loading ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />} {loading ? copy.analysing : copy.analyse} <ChevronRight size={16} /></button></div>
          </form>
          {error && <div className="error-message"><CircleAlert size={16} /> {error}</div>}
        </section>

        <section className="statute-strip" id="statutes"><div><span className="section-kicker">LEGAL DIRECTORY</span><h2>Key Indian legislation covered</h2></div><div className="statute-list"><span><b>RENTAL</b><strong>Rent Control Acts</strong><small>Tenancy, deposits, eviction</small></span><span><b>CRIMINAL</b><strong>BNS & BNSS</strong><small>Offences and procedure</small></span><span><b>CONSUMER</b><strong>Consumer Protection Act</strong><small>Defective goods and services</small></span><span><b>FAMILY</b><strong>Hindu Marriage Act</strong><small>Marriage and custody</small></span></div></section>

        {!hasSearched ? <EmptyState copy={copy} /> : <section className="results-area">
          <div className="results-heading"><div><span className="section-kicker">{copy.report}</span><h2>{copy.glance}</h2></div><span className="report-date">{copy.live}</span></div>
          <div className="metric-grid">
            <Metric
  icon={<ShieldCheck />}
  label={copy.winRate}
  value={winRate === null ? copy.insufficient : `${winRate}%`}
  detail={
    hasHistoricalRate
      ? `${outcome.comparable_cases || 0} ${copy.cases}`
      : result.prediction?.matched_case_type
        ? `No cases for "${result.prediction.matched_case_type}"`
        : `${outcome?.comparable_cases || 0} ${copy.outcomes}`
  }
  tone="gold"
  
/>

            <Metric icon={<Gavel />} label={copy.domain} value={result.legal_domain || copy.underReview} detail={copy.primary} />
            <Metric icon={<Clock3 />} label={copy.urgency} value={result.deadlines?.length ? copy.reviewDates : copy.assessTiming} detail={copy.deadline} />
          </div>
          <div className="dashboard-grid">
            <div className="dashboard-column">
              <article className="insight-card steps-card"><div className="card-title"><span className="icon-box accent"><ArrowUpRight size={17} /></span><div><span className="card-label">{copy.recommended}</span><h3>{copy.next}</h3></div></div><ol className="step-list">{getIssueSpecificSteps(result).slice(0, 7).map((step, index) => <li key={step}><span>{String(index + 1).padStart(2, '0')}</span><p>{step}</p></li>)}</ol>{!getIssueSpecificSteps(result).length && <p className="muted">{copy.noSteps}</p>}</article>
              <article className="insight-card answer-card"><div className="card-title"><span className="icon-box"><BookOpen size={17} /></span><div><span className="card-label">{copy.briefing}</span><h3>{copy.meaning}</h3></div></div><ul className="answer-points">{briefingPoints.map((point) => <li key={point}>{point}</li>)}</ul><div className="source-line"><FileText size={14} /> {copy.sourceNote}</div></article>
              {outcome && <article className="insight-card outcome-card"><div className="card-title"><span className="icon-box"><Gavel size={17} /></span><div><span className="card-label">{copy.historical}</span><h3>{copy.pastRate}</h3></div></div>{hasHistoricalRate ? <><div className="outcome-value">{winRate}<small>%</small></div><p>{outcome.basis || 'Observed favorable outcome rate among comparable cases.'}</p></> : <p className="muted">{outcome.comparable_cases || 0} {copy.outcomes}</p>}</article>}
            </div>
            <div className="dashboard-column">
              <article className="insight-card"><div className="card-title"><span className="icon-box"><FileText size={17} /></span><div><span className="card-label">{copy.references}</span><h3>{copy.sources}</h3></div></div><TagList items={getSources(result)} empty={copy.noSources} /></article>
              <article className="insight-card"><div className="card-title"><span className="icon-box"><BriefcaseBusiness size={17} /></span><div><span className="card-label">{copy.prepare}</span><h3>{copy.evidence}</h3></div></div><TagList items={result.evidence_to_collect} empty={copy.noEvidence} /></article>
            </div>
          </div>
          <div className="disclaimer"><CircleAlert size={18} /><div><strong>{copy.disclaimerTitle}</strong><p>{result.disclaimer || 'JusticeCompass provides general legal information only. Consult a qualified lawyer or legal-aid service for advice about your specific circumstances, current law, deadlines, and strategy.'}</p></div></div>
        </section>}
      </main>
      <footer><span>JUSTICECOMPASS / CASE INTELLIGENCE</span><span>Built for better first questions.</span></footer>
    </div>
  )
}

function Metric({ icon, label, value, detail, tone = '' }) { return <div className={`metric ${tone}`}><div className="metric-icon">{icon}</div><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></div> }
function TagList({ items, empty }) { return <div className="tag-list">{items?.length ? items.map((item) => <span className="law-tag" key={item}><Check size={13} />{item}</span>) : <p className="muted">{empty}</p>}</div> }
function EmptyState({ copy }) { return <section className="empty-state"><div className="empty-icon"><Scale size={24} /></div><div><span className="section-kicker">{copy.ready}</span><h2>{copy.readyTitle}</h2><p>{copy.readyText}</p></div><div className="empty-rule" /></section> }

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>)