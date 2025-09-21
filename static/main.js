let session_id = null;
let cwd = '/';
let history = [], histIndex = -1;

async function init() {
  const res = await fetch('/init');
  const j = await res.json();
  session_id = j.session_id;
  cwd = j.cwd || '/';
  document.getElementById('prompt').textContent = cwd + ' $';
  setupAutocomplete();
}
init();

document.getElementById('cmd').addEventListener('keydown', async (e) => {
  const input = e.target;
  if (e.key === 'Enter') {
    const cmd = input.value.trim();
    if (cmd) {
      history.push(cmd);
      histIndex = history.length;
      printLine(`$ ${cmd}`);
      input.value = '';
      await send(cmd);
      hideDropdown();
    }
  } else if (e.key === 'ArrowUp') {
    if (histIndex > 0) histIndex--;
    input.value = history[histIndex] || '';
    e.preventDefault();
  } else if (e.key === 'ArrowDown') {
    if (histIndex < history.length - 1) histIndex++;
    else { histIndex = history.length; input.value = ''; }
    input.value = history[histIndex] || '';
    e.preventDefault();
  } else if (e.key === 'Tab') {
    e.preventDefault();
    autoComplete(input);
  }
});

document.getElementById('cmd').addEventListener('blur', () => {
  hideDropdown();
});

function printLine(text) {
  const out = document.getElementById('output');
  out.innerText += text + '\n';
  out.scrollTop = out.scrollHeight;
}

async function send(command) {
  const res = await fetch('/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({session_id, command})
  });
  if (!res.ok) {
    printLine('Error: Server response failed');
    return;
  }
  const j = await res.json();
  if (j.editor) {
    openNano(j.editor);
  } else if (command.trim().toLowerCase() === 'clear' || command.trim().toLowerCase() === 'cls') {
    document.getElementById('output').innerText = '';
  } else if (j.output && j.output !== '') {
    printLine(j.output);
  }
  if (j.cwd) {
    cwd = j.cwd;
    document.getElementById('prompt').textContent = cwd + ' $';
  }
  if (j.cpu || j.memory) {
    updateMonitoringCharts(j.cpu, j.memory);
  }
}

function openNano(filename) {
  console.log("Opening nano for:", filename); // Debug
  fetch('/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({session_id, command: 'cat ' + filename})
  })
  .then(res => res.json())
  .then(j => {
    const content = j.output || '';
    console.log("Loaded content for", filename, ":", content); // Debug
    document.getElementById("nano-filename").innerText = filename;
    document.getElementById("nano-content").value = content;
    document.getElementById("nano-editor").style.display = "block";
    document.getElementById("nano-content").focus();
  })
  .catch(error => {
    console.error("Error loading nano:", error);
    printLine('Error: Failed to load file content');
  });
}

function saveNano() {
  const filename = document.getElementById("nano-filename").innerText;
  const content = document.getElementById("nano-content").value;
  fetch('/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({session_id, command: `nano ${filename}`, content: content})
  })
  .then(res => res.json())
  .then(j => {
    document.getElementById("nano-editor").style.display = "none"; // Ensure editor hides
    if (j.output) {
      printLine(j.output);
    }
    document.getElementById("cmd").focus(); // Return focus to terminal input
  })
  .catch(error => {
    printLine('Error: Failed to save');
    document.getElementById("nano-editor").style.display = "none"; // Hide on error
    document.getElementById("cmd").focus();
  });
}

function setupAutocomplete() {
  const input = document.getElementById('cmd');
  const dropdown = document.createElement('div');
  dropdown.id = 'command-dropdown';
  dropdown.style.position = 'absolute';
  dropdown.style.background = '#333';
  dropdown.style.color = '#fff';
  dropdown.style.maxHeight = '150px';
  dropdown.style.overflowY = 'auto';
  dropdown.style.display = 'none';
  document.getElementById('prompt-line').appendChild(dropdown);

  input.addEventListener('input', () => {
    const value = input.value.toLowerCase();
    if (value) {
      const suggestions = history.filter(cmd => cmd.toLowerCase().startsWith(value));
      updateHistoryDropdown(suggestions);
      if (suggestions.length > 0) {
        dropdown.style.display = 'block';
        dropdown.style.left = input.offsetLeft + 'px';
        dropdown.style.top = (input.offsetTop + input.offsetHeight) + 'px';
      } else {
        hideDropdown();
      }
    } else {
      hideDropdown();
    }
  });

  dropdown.addEventListener('click', (e) => {
    if (e.target.tagName === 'DIV') {
      input.value = e.target.textContent;
      hideDropdown();
      input.focus();
    }
  });
}

function updateHistoryDropdown(suggestions = history) {
  const dropdown = document.getElementById('command-dropdown');
  dropdown.innerHTML = '';
  suggestions.forEach(cmd => {
    const div = document.createElement('div');
    div.textContent = cmd;
    div.style.padding = '2px 5px';
    div.style.cursor = 'pointer';
    div.addEventListener('mouseover', () => div.style.background = '#555');
    div.addEventListener('mouseout', () => div.style.background = '');
    dropdown.appendChild(div);
  });
  dropdown.style.display = suggestions.length > 0 ? 'block' : 'none';
}

function hideDropdown() {
  const dropdown = document.getElementById('command-dropdown');
  if (dropdown) dropdown.style.display = 'none';
}

function autoComplete(input) {
  const value = input.value.toLowerCase();
  const suggestions = history.filter(cmd => cmd.toLowerCase().startsWith(value));
  if (suggestions.length > 0) {
    input.value = suggestions[0];
    hideDropdown();
  }
}

function updateMonitoringCharts(cpuData, memoryData) {
  if (!cpuData && !memoryData) return;
  if (cpuData) {
    const cpuChart = {
      type: 'line',
      data: { labels: ['Now'], datasets: [{ label: 'CPU Usage (%)', data: [cpuData], borderColor: '#FF6384', backgroundColor: 'rgba(255, 99, 132, 0.2)', fill: true }] },
      options: { responsive: true, scales: { y: { beginAtZero: true, max: 100 } } }
    };
    displayChart('cpuChart', cpuChart);
  }
  if (memoryData) {
    const memoryChart = {
      type: 'doughnut',
      data: { labels: ['Used', 'Free'], datasets: [{ data: [memoryData.percent, 100 - memoryData.percent], backgroundColor: ['#36A2EB', '#FFCE56'], borderColor: ['#36A2EB', '#FFCE56'], borderWidth: 1 }] },
      options: { responsive: true }
    };
    displayChart('memoryChart', memoryChart);
  }
}

function displayChart(chartId, chartConfig) {
  const canvas = document.createElement('canvas');
  canvas.id = chartId;
  canvas.style.width = '300px';
  canvas.style.height = '150px';
  document.getElementById('output').appendChild(canvas);
  console.log(`Chart ${chartId} configured:`, chartConfig);
}