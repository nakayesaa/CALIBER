import './styles.css';

const toast = document.querySelector('#toast');
let toastTimer;

function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 1800);
}

document.querySelectorAll('.nav-btn').forEach((button) => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.nav-btn').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    showToast(`${button.dataset.label} view selected`);
  });
});

document.querySelectorAll('.event-toggle').forEach((button) => {
  button.addEventListener('click', () => {
    const card = button.closest('.event-card');
    const expanded = card.classList.toggle('expanded');
    card.classList.toggle('compact', !expanded);
    button.setAttribute('aria-expanded', String(expanded));
  });
});

document.querySelector('#timeRange').addEventListener('change', (event) => {
  showToast(`Health trajectory: ${event.target.value}`);
});

document.querySelector('#assetPicker').addEventListener('click', () => {
  showToast('KO-3201 is the active hero asset');
});

document.querySelector('#assetSearch').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && event.target.value.trim()) {
    showToast(`Searching for “${event.target.value.trim()}”`);
  }
});

document.querySelector('.add-button').addEventListener('click', () => {
  showToast('New dashboard view');
});
