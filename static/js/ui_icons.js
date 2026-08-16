const UI_ICON_BASE = '/secret_scanner/static/icons/new/';

function uiIcon(name, className = 'ui-icon', size = 14) {
    return `<img src="${UI_ICON_BASE}${name}" alt="" class="${className}" width="${size}" height="${size}">`;
}

function uiIconLabel(icon, tint, text, size = 14) {
    return `<span class="inline-icon-label">${uiIcon(icon, 'ui-icon ' + tint, size)}<span>${text}</span></span>`;
}

function uiDetailHeading(icon, tint, text, hint = '') {
    const hintHtml = hint ? `<span class="detail-section-hint">${hint}</span>` : '';
    return `<h4 class="detail-section-title">${uiIcon(icon, 'ui-icon ' + tint, 16)}<span>${text}</span>${hintHtml}</h4>`;
}

function uiTh(icon, tint, text) {
    return `<span class="th-with-icon">${uiIcon(icon, 'ui-icon ' + tint, 14)}<span>${text}</span></span>`;
}

function statusConfirmedHtml(text = 'Confirmed') {
    return `<span class="status-confirmed status-with-icon">${uiIcon('CheckboxCheckedFilled.svg', 'icon-tint-success', 12)}<span>${text}</span></span>`;
}

function statusRefutedHtml(text = 'Refuted') {
    return `<span class="status-refuted status-with-icon">${uiIcon('Error.svg', 'icon-tint-error', 12)}<span>${text}</span></span>`;
}

function statusNoneHtml(text = 'No status') {
    return `<span class="status-none status-with-icon">${uiIcon('NoStatus.svg', 'icon-tint-muted', 12)}<span>${text}</span></span>`;
}

function iconActionBtn(icon, tint, text, extraClass = '') {
    return `<span class="icon-action-btn ${extraClass}">${uiIcon(icon, 'ui-icon ' + tint, 14)}<span>${text}</span></span>`;
}
