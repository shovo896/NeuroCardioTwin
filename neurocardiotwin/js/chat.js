/* Authenticated, transient research chat. The server owns all AI access. */
window.NCTChat = (() => {
  const $ = id => document.getElementById(id);
  const copy = {
    en: { greeting: 'Ask about your model result, signal validation, or the research workflow. I reply from approved knowledge only.', placeholder: 'Ask a research workflow question…', sending: 'Thinking…', error: 'The assistant is unavailable right now. Please try again.', note: 'Chat is not saved. Do not share personal data or raw signal samples. Research use only.' },
    bn: { greeting: 'মডেলের ফলাফল, signal validation বা গবেষণার workflow সম্পর্কে প্রশ্ন করুন। আমি শুধু অনুমোদিত জ্ঞানভিত্তিক উত্তর দিই।', placeholder: 'গবেষণা সম্পর্কিত প্রশ্ন লিখুন…', sending: 'উত্তর তৈরি হচ্ছে…', error: 'সহকারী এখন উপলব্ধ নয়। একটু পরে আবার চেষ্টা করুন।', note: 'চ্যাট সংরক্ষণ করা হয় না। ব্যক্তিগত তথ্য বা raw signal sample দেবেন না। এটি কেবল গবেষণার জন্য।' }
  };
  const escape = value => { const el = document.createElement('span'); el.textContent = value || ''; return el.innerHTML.replace(/\n/g, '<br>'); };
  function append(text, kind) { const root = $('chat-messages'); if (!root) return null; const item = document.createElement('article'); item.className = `chat-message ${kind}`; item.innerHTML = escape(text); root.append(item); root.scrollTop = root.scrollHeight; return item; }
  function language() { return $('chat-language')?.value === 'bn' ? 'bn' : 'en'; }
  function applyLanguage() { const words = copy[language()], input = $('chat-input'), messages = $('chat-messages'), note = document.querySelector('.chat-note'); if (input) input.placeholder = words.placeholder; if (note) note.innerHTML = `<i class="fa-solid fa-shield-halved"></i> ${words.note}`; if (messages && messages.children.length === 1 && messages.firstElementChild.classList.contains('assistant')) messages.firstElementChild.textContent = words.greeting; }
  function toggle(open) { const panel = $('research-chat'), launcher = $('chat-launcher'); if (!panel || !launcher) return; panel.hidden = !open; launcher.setAttribute('aria-expanded', String(open)); if (open) $('chat-input')?.focus(); }
  function init() {
    $('chat-launcher')?.addEventListener('click', () => toggle($('research-chat')?.hidden));
    $('chat-close')?.addEventListener('click', () => toggle(false));
    $('chat-language')?.addEventListener('change', applyLanguage);
    document.addEventListener('nct:language-change', event => {
      const picker = $('chat-language');
      if (picker && event.detail?.language) picker.value = event.detail.language;
      applyLanguage();
    });
    $('chat-form')?.addEventListener('submit', async event => {
      event.preventDefault(); const input = $('chat-input'), send = $('chat-send'), text = input?.value.trim();
      if (!text || !send) return;
      append(text, 'user'); input.value = ''; send.disabled = true;
      const pending = append(copy[language()].sending, 'assistant pending');
      try {
        const reply = await API.chat(text, language());
        pending?.remove(); append(reply.answer, 'assistant');
      } catch (error) {
        pending?.remove(); append(error.message || copy[language()].error, 'assistant error');
      } finally { send.disabled = false; input?.focus(); }
    });
    applyLanguage();
  }
  document.addEventListener('nct:authenticated', init, { once: true });
  return { init };
})();
