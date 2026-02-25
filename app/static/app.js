const form = document.getElementById('filters-form');
const message = document.getElementById('message');
const table = document.getElementById('results-table');
const tbody = table.querySelector('tbody');
const hintNodes = Array.from(document.querySelectorAll('.field-hint'));

function setMessage(text, type = 'info') {
  message.textContent = text;
  message.className = `message message-${type}`;
}

function setHint(field, text = '', state = 'neutral') {
  const el = hintNodes.find((node) => node.dataset.hintFor === field);
  if (!el) return;
  el.textContent = text;
  el.className = `field-hint ${state === 'ok' ? 'field-hint-ok' : state === 'bad' ? 'field-hint-bad' : ''}`;
}

function clearHints() {
  hintNodes.forEach((node) => {
    node.textContent = '';
    node.className = 'field-hint';
  });
}

function toPayload(formData) {
  const payload = {};
  for (const [key, value] of formData.entries()) {
    if (key === 'include_past') {
      payload[key] = value === 'on';
      continue;
    }
    if (value === '') continue;
    if (key === 'min_duration_h' || key === 'max_duration_h') {
      payload[key] = Number(value);
    } else {
      payload[key] = value.trim();
    }
  }
  if (!('include_past' in payload)) payload.include_past = false;
  return payload;
}

function contains(source, expected) {
  if (!expected) return true;
  if (!source) return false;
  return String(source).toLowerCase().includes(String(expected).toLowerCase());
}

function isFieldMatched(field, expected, flights) {
  if (expected === undefined || expected === null || expected === '') return true;

  return flights.some((f) => {
    if (field === 'min_duration_h') {
      return Number.isFinite(f.scheduled_duration_min) && f.scheduled_duration_min >= Number(expected) * 60;
    }
    if (field === 'max_duration_h') {
      return Number.isFinite(f.scheduled_duration_min) && f.scheduled_duration_min <= Number(expected) * 60;
    }
    if (field === 'departure_city_or_airport') {
      return (
        contains(f.departure_city, expected) ||
        contains(f.departure_airport, expected) ||
        contains(f.departure_airport_icao, expected)
      );
    }
    if (field === 'arrival_city_or_airport') {
      return contains(f.arrival_city, expected) || contains(f.arrival_airport, expected) || contains(f.arrival_airport_icao, expected);
    }
    if (field === 'arrival_airport') {
      return contains(f.arrival_airport, expected) || contains(f.arrival_airport_icao, expected);
    }
    if (field === 'airline') {
      return contains(f.airline, expected) || contains(f.callsign, expected) || contains(f.flight_number, expected);
    }
    return contains(f[field], expected);
  });
}

function updateFieldHints(payload, flights) {
  const fields = [
    'min_duration_h',
    'max_duration_h',
    'departure_country',
    'departure_city_or_airport',
    'arrival_country',
    'arrival_city_or_airport',
    'arrival_airport',
    'aircraft_icao',
    'airline',
  ];

  for (const field of fields) {
    const value = payload[field];
    if (value === undefined || value === null || value === '') {
      setHint(field, '');
      continue;
    }

    const matched = isFieldMatched(field, value, flights);
    if (matched) {
      setHint(field, '✓ Фильтр сработал', 'ok');
    } else {
      setHint(field, '✗ По этому фильтру совпадений нет', 'bad');
    }
  }
}

function renderFlights(flights) {
  tbody.innerHTML = '';
  flights.forEach((flight) => {
    const dep = [flight.departure_airport_icao, flight.departure_airport].filter(Boolean).join(' / ');
    const arr = [flight.arrival_airport_icao, flight.arrival_airport].filter(Boolean).join(' / ');

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${flight.callsign ?? '-'}</td>
      <td>${flight.flight_number ?? '-'}</td>
      <td>${flight.airline ?? '-'}</td>
      <td>${flight.aircraft_icao ?? '-'}</td>
      <td>${flight.departure_city ?? ''} (${dep || '-'})</td>
      <td>${flight.arrival_city ?? ''} (${arr || '-'})</td>
      <td>${flight.scheduled_duration_min ?? '-'}</td>
      <td>${flight.is_past ? 'Да' : 'Нет'}</td>
    `;
    tbody.appendChild(tr);
  });
}

form.addEventListener('reset', () => {
  tbody.innerHTML = '';
  table.hidden = true;
  clearHints();
  setMessage('Фильтры сброшены. Укажите параметры и начните новый поиск.', 'info');
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  setMessage('Загрузка данных из FlightRadar24...', 'info');
  table.hidden = true;
  const payload = toPayload(new FormData(form));

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 25000);

  try {
    const response = await fetch('/api/flights/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    const rawText = await response.text();
    let data = {};
    try {
      data = rawText ? JSON.parse(rawText) : {};
    } catch (_) {
      data = { detail: rawText || 'Сервер вернул не-JSON ответ.' };
    }

    if (!response.ok) {
      throw new Error(data.detail || `Ошибка запроса (HTTP ${response.status})`);
    }

    const flights = data.flights || [];
    renderFlights(flights);
    updateFieldHints(payload, flights);
    table.hidden = false;
    setMessage(`Найдено рейсов: ${data.count ?? flights.length}`, 'success');
  } catch (error) {
    if (error.name === 'AbortError') {
      setMessage('Поиск занял слишком много времени. Уточните фильтры (например ICAO аэропорта).', 'error');
    } else {
      setMessage(error.message, 'error');
    }
  } finally {
    clearTimeout(timer);
  }
});
