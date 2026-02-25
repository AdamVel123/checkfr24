const form = document.getElementById('filters-form');
const message = document.getElementById('message');
const table = document.getElementById('results-table');
const tbody = table.querySelector('tbody');


function setMessage(text, type = 'info') {
  message.textContent = text;
  message.className = `message message-${type}`;
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
      payload[key] = value;
    }
  }
  if (!('include_past' in payload)) payload.include_past = false;
  return payload;
}

function renderFlights(flights) {
  tbody.innerHTML = '';
  flights.forEach((flight) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${flight.callsign ?? '-'}</td>
      <td>${flight.flight_number ?? '-'}</td>
      <td>${flight.airline ?? '-'}</td>
      <td>${flight.aircraft_icao ?? '-'}</td>
      <td>${flight.departure_city ?? ''} (${flight.departure_airport ?? '-'})</td>
      <td>${flight.arrival_city ?? ''} (${flight.arrival_airport ?? '-'})</td>
      <td>${flight.scheduled_duration_min ?? '-'}</td>
      <td>${flight.is_past ? 'Да' : 'Нет'}</td>
    `;
    tbody.appendChild(tr);
  });
}


form.addEventListener('reset', () => {
  tbody.innerHTML = '';
  table.hidden = true;
  setMessage('Фильтры сброшены. Укажите параметры и начните новый поиск.', 'info');
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  setMessage('Загрузка данных из FlightRadar24...', 'info');

  table.hidden = true;
  const payload = toPayload(new FormData(form));

  try {
    const response = await fetch('/api/flights/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Ошибка запроса');
    }


    renderFlights(data.flights);
    table.hidden = false;
    setMessage(`Найдено рейсов: ${data.count}`, 'success');
  } catch (error) {
    setMessage(error.message, 'error');

  }
});
