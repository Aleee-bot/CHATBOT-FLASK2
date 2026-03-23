const input    = document.getElementById('userInput');
const sendBtn  = document.getElementById('sendBtn');
const messages = document.getElementById('chatMessages');

input.addEventListener('keydown', function(e) {
  if (e.key === 'Enter') sendMessage();
});

function scrollToBottom() {
  messages.scrollTop = messages.scrollHeight;
}

function addMessage(text, sender) {
  const row = document.createElement('div');
  row.className = 'message ' + sender;

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = sender === 'bot' ? '🌸' : '👤';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;

  row.appendChild(avatar);
  row.appendChild(bubble);
  messages.appendChild(row);
  scrollToBottom();
}

function addChartMessage(base64Image, caption, sender) {
  const row = document.createElement('div');
  row.className = 'message ' + sender;

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = sender === 'bot' ? '🌸' : '👤';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  
  // Create chart container
  const chartContainer = document.createElement('div');
  chartContainer.className = 'chart-container';
  
  // Add image
  const img = document.createElement('img');
  img.src = 'data:image/png;base64,' + base64Image;
  img.className = 'chart-image';
  img.style.maxWidth = '100%';
  img.style.height = 'auto';
  img.style.borderRadius = '8px';
  
  // Add caption
  const captionEl = document.createElement('div');
  captionEl.className = 'chart-caption';
  captionEl.textContent = caption;
  captionEl.style.marginTop = '8px';
  captionEl.style.fontSize = '13px';
  captionEl.style.textAlign = 'center';
  
  // Add download button (initially hidden)
  const downloadBtn = document.createElement('a');
  downloadBtn.className = 'download-btn';
  downloadBtn.href = 'data:image/png;base64,' + base64Image;
  downloadBtn.download = 'chart_' + new Date().getTime() + '.png';
  downloadBtn.textContent = '⬇️ Download Chart';
  downloadBtn.style.display = 'none';  // Hidden initially
  downloadBtn.style.marginTop = '8px';
  downloadBtn.style.padding = '6px 12px';
  downloadBtn.style.backgroundColor = '#3FB950';
  downloadBtn.style.color = 'white';
  downloadBtn.style.textDecoration = 'none';
  downloadBtn.style.borderRadius = '4px';
  downloadBtn.style.fontSize = '12px';
  downloadBtn.style.cursor = 'pointer';
  
  // Show download button only after image is fully loaded
  img.onload = function() {
    downloadBtn.style.display = 'inline-block';
  };
  
  // Handle image load errors
  img.onerror = function() {
    downloadBtn.textContent = '❌ Failed to load chart';
    downloadBtn.style.display = 'inline-block';
    downloadBtn.style.backgroundColor = '#F85149';
    downloadBtn.style.cursor = 'default';
  };
  
  chartContainer.appendChild(img);
  chartContainer.appendChild(captionEl);
  chartContainer.appendChild(downloadBtn);
  bubble.appendChild(chartContainer);

  row.appendChild(avatar);
  row.appendChild(bubble);
  messages.appendChild(row);
  scrollToBottom();
}

function showTyping() {
  const row = document.createElement('div');
  row.className = 'message bot typing';
  row.id = 'typingIndicator';

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = '🌸';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';

  row.appendChild(avatar);
  row.appendChild(bubble);
  messages.appendChild(row);
  scrollToBottom();
}

function removeTyping() {
  const el = document.getElementById('typingIndicator');
  if (el) el.remove();
}

function sendMessage() {
  const text = input.value.trim();
  if (!text) return;

  addMessage(text, 'user');
  input.value = '';
  sendBtn.disabled = true;
  input.disabled = true;  // Prevent sending multiple messages while processing

  showTyping();

  fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text })
  })
  .then(response => response.json())
  .then(data => {
    removeTyping();
    
    // Check if response includes a chart
    if (data.chart) {
      addChartMessage(data.chart, data.message, 'bot');
    } else {
      addMessage(data.message || data, 'bot');
    }
    
    sendBtn.disabled = false;
    input.disabled = false;  // Re-enable input
    input.focus();
  })
  .catch(error => {
    removeTyping();
    addMessage('Sorry, something went wrong. Please try again.', 'bot');
    sendBtn.disabled = false;
    input.disabled = false;  // Re-enable input on error
    input.focus();
  });
}

async function loadHistory() {
  try {
    const res = await fetch('/history');
    const data = await res.json();
 
    if (!data || data.length === 0) return;
    messages.innerHTML = '';
 
    data.forEach(msg => {
      const sender = msg.role === 'user' ? 'user' : 'bot';
      addMessage(msg.content, sender);
    });
  } catch (err) {
    console.error('Could not load chat history:', err);
  }
}
 
window.addEventListener('DOMContentLoaded', loadHistory);


function clearChat() {
  fetch('/clear_history', { method: 'POST' })
    .then(res => res.json())
    .then(() => {
      messages.innerHTML = '';
      addMessage("Hi! I'm your shop assistant.", 'bot');
    })
    .catch(() => {
      addMessage('Could not clear chat. Please try again.', 'bot');
    });
}