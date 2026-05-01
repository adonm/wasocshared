(() => {
  const input = document.getElementById('site-search-input');
  const results = document.getElementById('site-search-results');
  if (!input || !results) return;

  let indexPromise;
  const loadIndex = () => {
    indexPromise ||= fetch(`${window.location.origin}/index.json`).then((response) => response.ok ? response.json() : []);
    return indexPromise;
  };

  const normalise = (value) => (value || '').toString().toLowerCase();
  const snippet = (content, query) => {
    const text = (content || '').replace(/\s+/g, ' ').trim();
    const pos = normalise(text).indexOf(normalise(query));
    const start = Math.max(0, pos === -1 ? 0 : pos - 60);
    return `${start ? '…' : ''}${text.slice(start, start + 150)}${text.length > start + 150 ? '…' : ''}`;
  };

  const render = (items, query) => {
    results.innerHTML = '';
    if (!query) {
      results.classList.remove('is-open');
      return;
    }
    if (!items.length) {
      results.innerHTML = '<div class="search-result"><span class="search-result-title">No results</span></div>';
      results.classList.add('is-open');
      return;
    }
    const fragment = document.createDocumentFragment();
    items.slice(0, 8).forEach((item) => {
      const link = document.createElement('a');
      link.className = 'search-result';
      link.href = item.url;
      link.innerHTML = `<span class="search-result-section"></span><span class="search-result-title"></span><span class="search-result-snippet"></span>`;
      link.querySelector('.search-result-section').textContent = item.section || 'Page';
      link.querySelector('.search-result-title').textContent = item.title || item.url;
      link.querySelector('.search-result-snippet').textContent = snippet(item.content, query);
      fragment.appendChild(link);
    });
    results.appendChild(fragment);
    results.classList.add('is-open');
  };

  input.addEventListener('input', async () => {
    const query = input.value.trim();
    if (query.length < 2) return render([], '');
    const words = normalise(query).split(/\s+/).filter(Boolean);
    const pages = await loadIndex();
    const matches = pages
      .map((page) => {
        const haystack = normalise(`${page.title} ${page.section} ${page.content}`);
        if (!words.every((word) => haystack.includes(word))) return null;
        const titleHit = normalise(page.title).includes(normalise(query)) ? 5 : 0;
        const sectionHit = normalise(page.section).includes(normalise(query)) ? 2 : 0;
        return { ...page, score: titleHit + sectionHit };
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score || a.title.localeCompare(b.title));
    render(matches, query);
  });

  document.addEventListener('click', (event) => {
    if (!results.contains(event.target) && event.target !== input) results.classList.remove('is-open');
  });
})();
