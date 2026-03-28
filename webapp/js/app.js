const tg = window.Telegram.WebApp;

// App State
const state = {
    user: null,
    stats: { solved: 0, avg: 0, saved: 0 },
    schedule: [],
    homework: [],
    currentDate: new Date().toISOString().split('T')[0],
    activeTab: 'dashboard',
};

// DOM Elements
const elements = {
    loader: document.getElementById('loader'),
    userName: document.getElementById('user-name'),
    userAvatar: document.getElementById('user-avatar'),
    profileAvatarLarge: document.getElementById('profile-avatar-large'),
    profileFullName: document.getElementById('profile-full-name'),
    profileGrade: document.getElementById('profile-grade'),
    profileTgid: document.getElementById('profile-tg-id'),
    profileStatus: document.getElementById('profile-status'),
    statsSolved: document.getElementById('stats-solved'),
    statsAvg: document.getElementById('stats-avg'),
    statsSaved: document.getElementById('stats-saved'),
    dashboardDate: document.getElementById('dashboard-date'),
    scheduleDate: document.getElementById('active-date-display'),
    progressPercent: document.getElementById('progress-percent'),
    progressBarFill: document.getElementById('progress-bar-fill'),
    lessonsList: document.getElementById('lessons-list'),
    fullScheduleList: document.getElementById('full-schedule-list'),
    modalContainer: document.getElementById('modal-container'),
    modalTitle: document.getElementById('modal-title'),
    modalBody: document.getElementById('modal-body'),
    closeModal: document.querySelector('.close-modal'),
};

// Initialize App
function init() {
    tg.expand();
    tg.ready();
    
    // Apply Telegram Theme
    document.body.classList.toggle('dark', tg.colorScheme === 'dark');
    
    // Setup Navigation
    const tabs = document.querySelectorAll('.tab-btn');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // Close Modal on Overlay Click
    elements.modalContainer.addEventListener('click', (e) => {
        if (e.target === elements.modalContainer) closeModal();
    });
    elements.closeModal.addEventListener('click', closeModal);

    // Refresh Button
    document.getElementById('refresh-btn').addEventListener('click', () => {
        tg.HapticFeedback.notificationOccurred('success');
        fetchData();
    });

    // Date Navigation
    document.getElementById('prev-day').addEventListener('click', () => changeDate(-1));
    document.getElementById('next-day').addEventListener('click', () => changeDate(1));

    // Auth Actions
    document.getElementById('qr-auth-btn').addEventListener('click', () => {
        tg.showScanQrPopup({ text: 'Отсканируйте QR-код из личного кабинета' });
    });

    document.getElementById('token-auth-btn').addEventListener('click', () => {
        document.getElementById('token-input-area').style.display = 'block';
        document.getElementById('token-auth-btn').style.display = 'none';
    });

    document.getElementById('save-token-btn').addEventListener('click', () => {
        const token = document.getElementById('manual-token').value;
        if (token) {
            tg.showProgress();
            // Mock API call
            setTimeout(() => {
                tg.hideProgress();
                tg.showAlert('БРАВО! Теперь ты в системе. 🚀');
                fetchData();
                switchTab('dashboard');
            }, 1000);
        }
    });

    document.getElementById('what-is-token-link').addEventListener('click', (e) => {
        e.preventDefault();
        tg.showPopup({
            title: 'Что такое токен?',
            message: 'Токен - это твой цифровой ключ, который позволяет боту заходить в дневник под твоим именем и решать тесты. Это абсолютно безопасно.',
            buttons: [{type: 'ok', text: 'Понятно'}]
        });
    });

    // Logout Button
    document.getElementById('logout-btn').addEventListener('click', () => {
        tg.showConfirm('Вы уверены, что хотите удалить токен?', (confirmed) => {
            if (confirmed) {
                // Call API to delete token
                alert('Токен удален (демо)');
            }
        });
    });

    // Dashboard 'Solve All'
    document.getElementById('solve-all-dashboard-btn').addEventListener('click', () => {
        tg.showPopup({
            title: 'Массовое решение',
            message: 'Решить все доступные тесты на сегодня?',
            buttons: [
                {id: 'y', type: 'default', text: 'Да, решать всё!'},
                {id: 'n', type: 'cancel', text: 'Отмена'}
            ]
        }, (id) => {
            if (id === 'y') {
                tg.HapticFeedback.notificationOccurred('success');
                tg.showProgress();
                setTimeout(() => {
                    tg.hideProgress();
                    tg.showAlert('Все тесты на сегодня запущены в решение! 🚀');
                }, 1500);
            }
        });
    });

    // Load Initial Data
    fetchData();
}

// Switch Tabs
function switchTab(tabId) {
    state.activeTab = tabId;
    
    // Update UI
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabId);
    });
    
    document.querySelectorAll('.tab-view').forEach(view => {
        view.classList.toggle('active', view.id === `${tabId}-view`);
    });

    tg.HapticFeedback.impactOccurred('light');
}

// Change Date
function changeDate(days) {
    const date = new Date(state.currentDate);
    date.setDate(date.getDate() + days);
    state.currentDate = date.toISOString().split('T')[0];
    
    fetchData();
    tg.HapticFeedback.selectionChanged();
}

// Fetch Data from API
async function fetchData() {
    showLoader();
    
    const userId = tg.initDataUnsafe.user?.id || 12345; // Default for testing
    const initData = tg.initData;

    try {
        // In real app: const response = await fetch(`/api/user_data?userId=${userId}`, { headers: { 'Authorization': `TWA ${initData}` } });
        // Mocking data for now
        
        state.user = {
            id: userId,
            first_name: tg.initDataUnsafe.user?.first_name || 'Студент',
            last_name: tg.initDataUnsafe.user?.last_name || '',
            grade: '11А',
            status: '✅ Подключен'
        };

        state.stats = {
            solved: 124,
            avg: 4.8,
            saved: 1200
        };

        // Fetch Schedule & Homework
        state.schedule = [
            { id: 1, time: '08:30-09:10', room: '101', subject: 'МАТЕМАТИКА', type: 'lesson' },
            { id: 2, time: '09:20-10:00', room: '204', subject: 'РУССКИЙ ЯЗ.', type: 'lesson' },
            { id: 3, time: '10:15-10:55', room: '305', subject: 'ХИМИЯ', type: 'lesson' },
            { id: 4, time: '11:10-11:50', room: '102', subject: 'ОБЩЕСТВОЗНАНИЕ', type: 'lesson' },
            { id: 5, time: '12:10-12:50', room: 'Спортзал', subject: 'ФИЗКУЛЬТУРА', type: 'lesson' }
        ];

        state.homework = [
            { lesson_id: 1, text: 'Решить задачи на стр. 45 №1, 2, 3. Подготовиться к тесту по производным.', status: 'pending', type: 'written', links: [{title: 'Тренажер', link: 'https://school.mos.ru'}] },
            { lesson_id: 2, text: 'Прочитать параграф 7, ответить на вопросы устно.', status: 'done', type: 'theory' },
            { lesson_id: 3, text: 'Пройти обязательный онлайн тест МЭШ до субботы.', status: 'pending', type: 'test', links: [{title: 'Пройти тест', link: 'https://uchebnik.mos.ru'}] },
            { lesson_id: 4, text: 'Нет домашнего задания', status: 'none', type: 'none' }
        ];

        renderUI();
    } catch (error) {
        console.error('Fetch error:', error);
        tg.showAlert('Ошибка при загрузке данных: ' + error.message);
    } finally {
        hideLoader();
    }
}

// Render UI Components
function renderUI() {
    // User Info
    const displayName = state.user.first_name;
    elements.userName.textContent = displayName;
    elements.userAvatar.textContent = displayName[0].toUpperCase();
    elements.profileAvatarLarge.textContent = displayName[0].toUpperCase();
    elements.profileFullName.textContent = `${state.user.first_name} ${state.user.last_name}`;
    elements.profileGrade.textContent = `Класс: ${state.user.grade}`;
    elements.profileTgid.textContent = state.user.id;
    elements.profileStatus.textContent = state.user.status;

    // Stats
    elements.statsSolved.textContent = state.stats.solved;
    elements.statsAvg.textContent = state.stats.avg.toFixed(1);
    elements.statsSaved.textContent = state.stats.saved;

    // Dates
    const today = new Date();
    const isToday = state.currentDate === today.toISOString().split('T')[0];
    const dateFormatted = new Date(state.currentDate).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', weekday: 'long' });
    
    elements.dashboardDate.textContent = dateFormatted;
    elements.scheduleDate.textContent = isToday ? 'Сегодня' : dateFormatted;

    // Progress
    const total = state.homework.filter(h => h.status !== 'none').length;
    const done = state.homework.filter(h => h.status === 'done').length;
    const percent = total > 0 ? Math.round((done / total) * 100) : 100;
    
    elements.progressPercent.textContent = `${percent}%`;
    elements.progressBarFill.style.width = `${percent}%`;

    // Lessons List (Dashboard Preview)
    elements.lessonsList.innerHTML = '';
    state.schedule.slice(0, 3).forEach(lesson => {
        const hw = state.homework.find(h => h.lesson_id === lesson.id);
        const card = createLessonCard(lesson, hw);
        elements.lessonsList.appendChild(card);
    });

    // Schedule List
    elements.fullScheduleList.innerHTML = '';
    state.schedule.forEach(lesson => {
        const hw = state.homework.find(h => h.lesson_id === lesson.id);
        const card = createLessonCard(lesson, hw);
        elements.fullScheduleList.appendChild(card);
    });
}

function createLessonCard(lesson, hw) {
    const template = document.getElementById('lesson-card-template');
    const clone = template.content.cloneNode(true);
    const card = clone.querySelector('.lesson-card');
    
    card.querySelector('.time').textContent = lesson.time.split('-')[0];
    card.querySelector('.room').textContent = lesson.room || '';
    card.querySelector('.lesson-subject').textContent = lesson.subject;
    
    if (hw) {
        card.querySelector('.lesson-hw-desc').textContent = hw.text;
        const statusIcon = card.querySelector('.status-icon');
        statusIcon.classList.add(hw.status);
        if (hw.type === 'test') statusIcon.classList.add('test');
        
        card.addEventListener('click', () => openHomeworkDetail(lesson, hw));
    } else {
        card.querySelector('.lesson-hw-desc').textContent = 'Добазаться с учителем...';
        card.querySelector('.status-icon').classList.add('none');
    }
    
    return card;
}

// Modal Detail View
function openHomeworkDetail(lesson, hw) {
    elements.modalTitle.textContent = lesson.subject;
    
    let html = `
        <div class="homework-detail">
            <div class="homework-description">${hw.text}</div>
    `;
    
    if (hw.links && hw.links.length > 0) {
        html += `<div class="homework-links">`;
        hw.links.forEach(link => {
            html += `
                <a href="${link.link}" target="_blank" class="material-link">
                    <span class="material-icon">⚡</span>
                    <span class="link-title">${link.title}</span>
                </a>
            `;
        });
        html += `</div>`;
    }
    
    if (hw.type === 'test' && hw.status !== 'done') {
        html += `
            <div class="solve-actions">
                <button class="btn primary" id="solve-btn">🚀 РЕШИТЬ ИИ</button>
            </div>
        `;
    } else if (hw.status !== 'done' && hw.status !== 'none') {
        html += `
            <div class="solve-actions">
                <button class="btn secondary" id="mark-done-btn">✅ ОТМЕТИТЬ КАК ВЫПОЛНЕННОЕ</button>
            </div>
        `;
    }

    html += `</div>`;
    
    elements.modalBody.innerHTML = html;
    elements.modalContainer.classList.add('active');

    // Attach listeners after injection
    const solveBtn = document.getElementById('solve-btn');
    if (solveBtn) {
        solveBtn.addEventListener('click', () => {
            tg.HapticFeedback.impactOccurred('medium');
            tg.showPopup({
                title: 'Решение теста',
                message: 'Выберите точность решения:',
                buttons: [
                    {id: 'p', type: 'default', text: 'Идеально (95%)'},
                    {id: 'a', type: 'default', text: 'Нормально (85%)'},
                    {id: 'c', type: 'cancel', text: 'Отмена'}
                ]
            }, (btnId) => {
                if (btnId !== 'c') {
                    tg.showProgress();
                    setTimeout(() => {
                        tg.hideProgress();
                        tg.showAlert('Тест запущен в решение! Статус обновится автоматически.');
                        closeModal();
                    }, 1500);
                }
            });
        });
    }

    const markDoneBtn = document.getElementById('mark-done-btn');
    if (markDoneBtn) {
        markDoneBtn.addEventListener('click', () => {
            hw.status = 'done';
            tg.HapticFeedback.notificationOccurred('success');
            renderUI();
            closeModal();
        });
    }
}

function closeModal() {
    elements.modalContainer.classList.remove('active');
}

function showLoader() {
    elements.loader.style.opacity = '1';
    elements.loader.style.display = 'flex';
    document.body.classList.add('loading');
}

function hideLoader() {
    elements.loader.style.opacity = '0';
    setTimeout(() => {
        elements.loader.style.display = 'none';
        document.body.classList.remove('loading');
    }, 500);
}

// Run init
document.addEventListener('DOMContentLoaded', init);
