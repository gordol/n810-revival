/* A still-frame alternative for the animated desktop capture. */
(() => {
  const image = document.getElementById('home-desktop');
  const button = document.getElementById('home-motion');
  if (!image || !button) return;
  const animated = image.getAttribute('src');
  const still = image.dataset.still;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const source = image.parentElement.querySelector('source');
  let playing = !reduced.matches;
  const show = () => {
    image.src = playing ? animated : still;
    if (source) source.srcset = image.src;
    button.textContent = playing ? 'Pause animation' : 'Play animation';
  };
  button.hidden = false;
  button.addEventListener('click', () => { playing = !playing; show(); });
  reduced.addEventListener('change', () => { playing = !reduced.matches; show(); });
  show();
})();
