/* Authenticated, transient research chat. The server owns all AI access. */
window.NCTChat = (() => {
  const $ = id => document.getElementById(id);
  const copy = {
    en: { greeting: 'Ask in your own language about a model result, research workflow, or a general health concern. I provide safe general information—not a diagnosis or emergency service.', placeholder: 'Ask in any language…', sending: 'Thinking…', error: 'The assistant is unavailable right now. Please try again.', note: 'Chat is not saved. Do not share personal data or raw signal samples. For urgent symptoms in Bangladesh, call 999.' },
    bn: { greeting: 'মডেলের ফলাফল, গবেষণার workflow বা সাধারণ স্বাস্থ্য-উদ্বেগ সম্পর্কে প্রশ্ন করুন। আমি সাধারণ নিরাপদ তথ্য দিই—রোগ নির্ণয় নয়।', placeholder: 'স্বাস্থ্য বা গবেষণা-সম্পর্কিত প্রশ্ন লিখুন…', sending: 'উত্তর তৈরি হচ্ছে…', error: 'সহকারী এখন উপলব্ধ নয়। একটু পরে আবার চেষ্টা করুন।', note: 'চ্যাট সংরক্ষণ করা হয় না। ব্যক্তিগত তথ্য বা raw signal sample দেবেন না। জরুরি উপসর্গে বাংলাদেশে ৯৯৯-এ কল করুন।' }
  };
  const emergencyCopy = {
    en: { title: 'Emergency support', trigger: 'Emergency help', intro: 'Do not wait for a model result or chat reply if there is a possible emergency.', signs: 'Get emergency help now for chest pressure or pain, severe trouble breathing, fainting or unresponsiveness, sudden confusion, seizure, severe bleeding, or a risk of self-harm.', call: 'Call National Emergency Service 999', outside: 'Outside Bangladesh? Call your local emergency number.', steps: ['Tell someone nearby and do not stay alone.', 'If possible, unlock the door and keep your phone with you.', 'Do not drive yourself when feeling faint, confused, or severely unwell.'], disclaimer: 'This tool cannot diagnose an emergency. If in doubt, seek urgent in-person care.' },
    bn: { title: 'জরুরি সহায়তা', trigger: 'জরুরি সহায়তা', intro: 'জরুরি অবস্থা মনে হলে model result বা chat-এর উত্তরের জন্য অপেক্ষা করবেন না।', signs: 'বুকব্যথা বা বুকে চাপ, তীব্র শ্বাসকষ্ট, অজ্ঞান হওয়া বা সাড়া না দেওয়া, হঠাৎ বিভ্রান্তি, খিঁচুনি, অতিরিক্ত রক্তপাত, বা নিজেকে ক্ষতি করার ঝুঁকি থাকলে এখনই জরুরি সহায়তা নিন।', call: 'জাতীয় জরুরি সেবা ৯৯৯-এ কল করুন', outside: 'বাংলাদেশের বাইরে থাকলে স্থানীয় জরুরি নম্বরে কল করুন।', steps: ['কাছের কাউকে জানান এবং একা থাকবেন না।', 'সম্ভব হলে দরজা খুলে রাখুন এবং ফোন সঙ্গে রাখুন।', 'মাথা ঘোরা, বিভ্রান্তি বা খুব খারাপ লাগলে নিজে গাড়ি চালাবেন না।'], disclaimer: 'এই টুল জরুরি অবস্থা নির্ণয় করতে পারে না। সন্দেহ হলে দ্রুত সরাসরি চিকিৎসাসেবা নিন।' }
  };
  const escape = value => { const el = document.createElement('span'); el.textContent = value || ''; return el.innerHTML.replace(/\n/g, '<br>'); };
  function append(text, kind) { const root = $('chat-messages'); if (!root) return null; const item = document.createElement('article'); item.className = `chat-message ${kind}`; item.innerHTML = escape(text); root.append(item); root.scrollTop = root.scrollHeight; return item; }
  function language() { return $('chat-language')?.value || 'auto'; }
  function interfaceLanguage() { return window.NCTI18n?.language === 'bn' ? 'bn' : 'en'; }
  function emergencyLanguage() { return $('emergency-language')?.value === 'bn' ? 'bn' : 'en'; }
  function renderEmergency() {
    const selected = emergencyLanguage(), words = emergencyCopy[selected], root = $('emergency-content'), title = $('emergency-title'), trigger = $('emergency-launcher'), kicker = $('emergency-kicker'), close = $('emergency-close');
    if (!root) return;
    if (title) title.textContent = words.title;
    if (trigger) trigger.querySelector('span').textContent = words.trigger;
    if (kicker) kicker.textContent = selected === 'bn' ? 'জরুরি হলে এখনই পদক্ষেপ নিন' : 'ACT NOW IF URGENT';
    if (close) close.setAttribute('aria-label', selected === 'bn' ? 'জরুরি সহায়তা বন্ধ করুন' : 'Close emergency support');
    root.innerHTML = `<p class="emergency-intro">${words.intro}</p><p class="emergency-signs">${words.signs}</p><a class="emergency-call" href="tel:999"><i class="fa-solid fa-phone-volume"></i>${words.call}</a><p class="emergency-outside">${words.outside}</p><ol>${words.steps.map(step => `<li>${step}</li>`).join('')}</ol><p class="emergency-disclaimer"><i class="fa-solid fa-shield-heart"></i>${words.disclaimer}</p>`;
  }
  function toggleEmergency(open) { const panel = $('emergency-support'), launcher = $('emergency-launcher'); if (!panel || !launcher) return; renderEmergency(); panel.hidden = !open; launcher.setAttribute('aria-expanded', String(open)); if (open) $('emergency-close')?.focus(); }
  function applyLanguage() { const words = copy[interfaceLanguage()], input = $('chat-input'), messages = $('chat-messages'), note = document.querySelector('.chat-note'); if (input) input.placeholder = words.placeholder; if (note) note.innerHTML = `<i class="fa-solid fa-shield-halved"></i> ${words.note}`; if (messages && messages.children.length === 1 && messages.firstElementChild.classList.contains('assistant')) messages.firstElementChild.textContent = words.greeting; }
  function toggle(open) { const panel = $('research-chat'), launcher = $('chat-launcher'); if (!panel || !launcher) return; panel.hidden = !open; launcher.setAttribute('aria-expanded', String(open)); if (open) $('chat-input')?.focus(); }
  function init() {
    $('chat-launcher')?.addEventListener('click', () => toggle($('research-chat')?.hidden));
    $('chat-close')?.addEventListener('click', () => toggle(false));
    $('chat-language')?.addEventListener('change', applyLanguage);
    $('emergency-launcher')?.addEventListener('click', () => toggleEmergency($('emergency-support')?.hidden));
    $('emergency-close')?.addEventListener('click', () => toggleEmergency(false));
    $('emergency-language')?.addEventListener('change', renderEmergency);
    document.addEventListener('nct:language-change', event => {
      const picker = $('chat-language');
      const emergencyPicker = $('emergency-language');
      if (emergencyPicker && event.detail?.language) emergencyPicker.value = event.detail.language;
      applyLanguage();
      renderEmergency();
    });
    $('chat-form')?.addEventListener('submit', async event => {
      event.preventDefault(); const input = $('chat-input'), send = $('chat-send'), text = input?.value.trim();
      if (!text || !send) return;
      append(text, 'user'); input.value = ''; send.disabled = true;
      const pending = append(copy[interfaceLanguage()].sending, 'assistant pending');
      try {
        const reply = await API.chat(text, language());
        pending?.remove(); append(reply.answer, 'assistant');
      } catch (error) {
        pending?.remove(); append(error.message || copy[interfaceLanguage()].error, 'assistant error');
      } finally { send.disabled = false; input?.focus(); }
    });
    applyLanguage();
    renderEmergency();
  }
  document.addEventListener('nct:authenticated', init, { once: true });
  return { init };
})();
