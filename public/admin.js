async function fetchSessions() {
  try {
    const res = await fetch('/sessions');
    const data = await res.json();
    const wrap = document.getElementById('sessions');
    wrap.innerHTML = '';
    const keys = Object.keys(data);
    if (keys.length === 0) {
      wrap.innerHTML = '<div class="empty">No active sessions</div>';
      return;
    }
    const ul = document.createElement('ul');
    keys.forEach(k => {
      const li = document.createElement('li');
      const info = data[k];
      const last = new Date(info.last_seen || Date.now()).toLocaleString();
      const has = info.has_image ? '🟢' : '⚪';
      li.innerHTML = `<strong>${k}</strong> ${has} &nbsp; last: ${last} &nbsp; <a href="/view/${encodeURIComponent(k)}?password=${encodeURIComponent(document.getElementById('password').value||'@MadMax31')}" target="_blank">View</a>`;
      ul.appendChild(li);
    });
    wrap.appendChild(ul);
  } catch (e) {
    document.getElementById('sessions').innerText = 'Failed to load';
    console.error(e);
  }
}

document.getElementById('viewBtn').addEventListener('click', () => {
  const sid = document.getElementById('session').value.trim();
  const pwd = document.getElementById('password').value;
  if (!sid) return alert('enter session id');
  const url = `/view/${encodeURIComponent(sid)}?password=${encodeURIComponent(pwd)}`;
  window.open(url, '_blank');
});

fetchSessions();
setInterval(fetchSessions, 5000);
