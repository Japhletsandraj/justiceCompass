const form = document.getElementById('assessmentForm');
const questionInput = document.getElementById('question');
const detailsSection = document.getElementById('detailsSection');
const toggleDetailsBtn = document.getElementById('toggleDetailsBtn');
const fetchExternalSources = document.getElementById('fetchExternalSources');
const fetchFullJudgments = document.getElementById('fetchFullJudgments');
const liveCostWarning = document.getElementById('liveCostWarning');
const errorBanner = document.getElementById('errorBanner');
const emptyState = document.getElementById('emptyState');
const loadingState = document.getElementById('loadingState');
const resultContainer = document.getElementById('resultContainer');
const submitBtn = document.getElementById('submitBtn');
const newAssessmentBtn = document.getElementById('newAssessmentBtn');

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.classList.remove('hidden');
}

function clearError() {
  errorBanner.textContent = '';
  errorBanner.classList.add('hidden');
}

function setLoading(isLoading) {
  submitBtn.disabled = isLoading;
  loadingState.classList.toggle('hidden', !isLoading);
  emptyState.classList.toggle('hidden', isLoading || resultContainer.innerHTML.trim() !== '');
}

function resetResultState() {
  resultContainer.classList.add('hidden');
  resultContainer.innerHTML = '';
  emptyState.classList.remove('hidden');
}

function safeArray(value) {
  if (!Array.isArray(value)) return [];
  return value;
}

function fieldList(items) {
  if (!items || !items.length) return '<p class="muted">No items listed.</p>';
  return `<ul>${items.map((item) => `<li>${item}</li>`).join('')}</ul>`;
}

function renderCaseReferences(cases) {
  const entries = safeArray(cases);
  if (!entries.length) {
    return '<p class="muted">No case references were returned.</p>';
  }

  return entries
    .map(
      (item) => `
        <div class="case-reference">
          <strong>${item.case_number || item.document_id || 'Case reference'}</strong>
          <div class="muted">${item.title || 'Untitled case'}</div>
          <div>${item.outcome || item.result || 'Outcome not confidently extracted'}</div>
        </div>
      `
    )
    .join('');
}

function renderPrediction(prediction) {
  if (!prediction || prediction.estimate === null || prediction.estimate === undefined) {
    return `
      <div class="result-card">
        <h3>Prediction</h3>
        <p><strong>Insufficient comparable outcome data.</strong></p>
        <p class="muted">The system does not have enough comparable judgments to provide a reliable historical outcome estimate.</p>
      </div>
    `;
  }

  const basis = prediction.basis || 'Comparable judgments';
  const sampleSize = prediction.sample_size ?? prediction.sampleSize ?? 'N/A';
  const lowerBound = prediction.lower_bound ?? prediction.lowerBound ?? 'N/A';
  const upperBound = prediction.upper_bound ?? prediction.upperBound ?? 'N/A';
  const limitations = prediction.limitations || 'The estimate is only directional and depends on the quality of the available comparable cases.';

  return `
    <div class="result-card">
      <h3>Prediction score</h3>
      <div class="meta-row">
        <span class="badge">${Number(prediction.estimate).toFixed(1)}%</span>
      </div>
      <p><strong>Historical favorable-outcome rate among comparable judgments:</strong> ${Number(prediction.estimate).toFixed(1)}%.</p>
      <ul>
        <li><strong>Basis:</strong> ${basis}</li>
        <li><strong>Sample size:</strong> ${sampleSize}</li>
        <li><strong>Bounds:</strong> ${lowerBound}% to ${upperBound}%</li>
        <li><strong>Limitations:</strong> ${limitations}</li>
      </ul>
    </div>
  `;
}

function renderResult(data) {
  const structured = data.structured_answer || {};
  const concern = data.concern_assessment || 'No issue summary was returned.';
  const legalIssues = safeArray(data.legal_issues);
  const applicableLaws = safeArray(data.applicable_laws);
  const immediateSteps = safeArray(data.immediate_steps);
  const evidence = safeArray(data.evidence_to_collect);
  const missingInformation = safeArray(data.missing_information);
  const sourceCitations = safeArray(data.source_citations);
  const externalSources = safeArray(data.external_sources);
  const caseReferences = safeArray(structured.case_references || data.case_references || []);
  const confidenceLabel = data.confidence_label || 'Low';
  const confidenceScore = typeof data.confidence_score === 'number' ? data.confidence_score.toFixed(2) : 'N/A';

  const resultHtml = `
    <div class="result-card">
      <h3>Assessment</h3>
      <div class="meta-row">
        <span class="badge">${confidenceLabel}</span>
        <span class="badge">confidence ${confidenceScore}</span>
        <span class="badge">${data.legal_domain || 'Unknown legal domain'}</span>
      </div>
      <p>${concern}</p>
      <div class="inline-actions">
        <button class="secondary-btn" type="button" id="copySummaryBtn">Copy summary</button>
        <button class="ghost-btn" type="button" id="contactAidBtn">Contact legal aid</button>
      </div>
    </div>

    <div class="result-card">
      <h3>Can this be registered?</h3>
      <p>${structured.registrable_assessment || 'The registration pathway could not be assessed from the available information.'}</p>
    </div>

    <div class="result-card">
      <h3>Conditions and forum</h3>
      ${fieldList(structured.registration_conditions || data.possible_forums || [])}
      <p><strong>Forum:</strong> ${structured.registration_forum || data.possible_forums?.[0] || 'To be confirmed with local counsel.'}</p>
    </div>

    <div class="result-card">
      <h3>Applicable law</h3>
      <p><strong>Likely legal issues:</strong></p>
      ${fieldList(legalIssues)}
      <p><strong>Applicable laws:</strong></p>
      ${fieldList(applicableLaws.length ? applicableLaws : data.applicable_laws || [])}
      ${sourceCitations.length ? `<p><strong>Citations:</strong> ${sourceCitations.join(', ')}</p>` : '<p class="muted">No sources were cited.</p>'}
    </div>

    <div class="result-card">
      <h3>Case references</h3>
      ${renderCaseReferences(caseReferences)}
    </div>

    ${renderPrediction(data.historical_outcome_estimate)}

    <div class="result-card">
      <h3>Next steps</h3>
      ${fieldList(structured.next_steps || immediateSteps)}
      <p><strong>Immediate steps:</strong></p>
      ${fieldList(immediateSteps)}
      <p><strong>Evidence to collect:</strong></p>
      ${fieldList(evidence)}
    </div>

    <div class="result-card">
      <h3>Missing information</h3>
      ${fieldList(missingInformation.length ? missingInformation : data.missing_information || [])}
    </div>

    <div class="result-card">
      <h3>Sources</h3>
      ${sourceCitations.length ? `<ul>${sourceCitations.map((source) => `<li>${source}</li>`).join('')}</ul>` : '<p class="muted">No authoritative source citations were returned.</p>'}
      ${externalSources.length ? `
        <div>
          <p><strong>Live external sources:</strong></p>
          <ul class="link-list">
            ${externalSources
              .map(
                (source) => `
                  <li>
                    <a href="${source.source_url || '#'}" target="_blank" rel="noreferrer">
                      ${source.title || 'View source'}
                    </a>
                  </li>
                `
              )
              .join('')}
          </ul>
        </div>
      ` : ''}
    </div>

    <div class="result-card">
      <h3>Disclaimer</h3>
      <p>${data.disclaimer || 'This is general legal information and not formal legal advice.'}</p>
    </div>
  `;

  resultContainer.innerHTML = resultHtml;
  resultContainer.classList.remove('hidden');
  emptyState.classList.add('hidden');

  const copyBtn = document.getElementById('copySummaryBtn');
  const contactBtn = document.getElementById('contactAidBtn');

  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      const text = [
        'JusticeCompass summary',
        `Question: ${questionInput.value.trim()}`,
        `Concern: ${concern}`,
        `Registration: ${structured.registrable_assessment || 'Not available'}`,
        `Next steps: ${safeArray(immediateSteps).join(' | ') || 'N/A'}`,
        `Sources: ${sourceCitations.join(', ') || 'N/A'}`,
      ].join('\n');

      try {
        await navigator.clipboard.writeText(text);
        copyBtn.textContent = 'Copied';
        setTimeout(() => {
          copyBtn.textContent = 'Copy summary';
        }, 1500);
      } catch (error) {
        showError('Copy failed, but the result is still visible below.');
      }
    });
  }

  if (contactBtn) {
    contactBtn.addEventListener('click', () => {
      window.open('https://nalsa.gov.in/', '_blank', 'noopener,noreferrer');
    });
  }
}

async function submitAssessment(event) {
  event.preventDefault();
  clearError();

  const question = questionInput.value.trim();
  if (!question || question.length < 8) {
    showError('Please provide a clearer description of the issue before submitting.');
    questionInput.focus();
    return;
  }

  const payload = {
    question,
    jurisdiction: document.getElementById('jurisdiction').value.trim() || null,
    date_context: document.getElementById('dateContext').value.trim() || null,
    case_type: document.getElementById('caseType').value || null,
    region: document.getElementById('region').value.trim() || null,
    cited_section: document.getElementById('citedSection').value.trim() || null,
    fetch_external_sources: fetchExternalSources.checked,
    fetch_full_judgments: fetchFullJudgments.checked,
    max_full_judgments: Number(document.getElementById('maxFullJudgments').value || 5),
    include_rag_answer: true,
  };

  setLoading(true);

  try {
    const response = await fetch('/assess', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'The assessment service could not answer the request.');
    }

    renderResult(data);
  } catch (error) {
    showError(error.message || 'Something went wrong while contacting the API.');
    resultContainer.classList.add('hidden');
    emptyState.classList.remove('hidden');
  } finally {
    setLoading(false);
  }
}

function handleExternalSourcesToggle() {
  if (fetchExternalSources.checked) {
    const confirmed = window.confirm('Live Indian Kanoon search may incur metered usage costs. Continue?');
    if (!confirmed) {
      fetchExternalSources.checked = false;
      return;
    }
  }

  liveCostWarning.classList.toggle('hidden', !fetchExternalSources.checked);
}

function handleFullJudgmentToggle() {
  const enabled = fetchFullJudgments.checked;
  if (enabled) {
    window.alert('Full judgment fetching can increase cost and response time. The maximum count is 20.');
  }
}

form.addEventListener('submit', submitAssessment);
fetchExternalSources.addEventListener('change', handleExternalSourcesToggle);
fetchFullJudgments.addEventListener('change', handleFullJudgmentToggle);

toggleDetailsBtn.addEventListener('click', () => {
  detailsSection.classList.toggle('hidden');
  toggleDetailsBtn.textContent = detailsSection.classList.contains('hidden') ? 'Add details' : 'Hide details';
});

newAssessmentBtn.addEventListener('click', () => {
  form.reset();
  fetchExternalSources.checked = false;
  fetchFullJudgments.checked = false;
  liveCostWarning.classList.add('hidden');
  clearError();
  resetResultState();
  questionInput.focus();
});

resetResultState();
