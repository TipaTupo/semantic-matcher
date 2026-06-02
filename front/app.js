// Semantic Search Frontend Application
// Pure JavaScript implementation without external dependencies

(function () {
    'use strict';

    // API Base URL (empty for same origin)
    const API_BASE = '';

    // State
    let activeVersionId = null;
    let currentVersionId = null;
    let healthCheckInterval = null;

    // Pinned task state
    let pinnedTaskId = null;
    let pinnedTaskCard = null;
    let pinnedTaskInterval = null;

    // DOM Elements
    const elements = {};


    // Index JSON placeholder
    const indexJsonPlaceholder = `
        [
            {
                "id": "article_001",
                "title": "Заголовок",
                "samples": [
                    "пример вопроса 1",
                    "пример вопроса 2"
                ]
            }
        ]
    `.trim().replaceAll("\n        ", '\n');

    // Слушатель события изменения размера страницы
    function handlePageWidthChange(event) {
        if (event.matches) {
            document.querySelector(".sidebar").classList.remove("open");
            document.querySelector('header .icon-wrapper[desc="wrapper menu"]').setAttribute("onclick", "expandSidebar(event)");
        } else {
            document.querySelector(".sidebar").classList.add("open");
            document.querySelector('header .icon-wrapper[desc="wrapper menu"]').setAttribute("onclick", "collapseSidebar(event)");
        }
    }

    // Медиа-условие (меньше или равно 768px)
    const pageWidth = window.matchMedia('(max-width: 768px)');
    pageWidth.addEventListener('change', handlePageWidthChange);

    // Initialize application
    function init() {
        cacheElements();
        setupEventListeners();
        startHealthCheck();
        showPage('search');
        handlePageWidthChange(pageWidth);
    }

    // Cache DOM elements
    function cacheElements() {

        // SVG path icons
        elements.icons = {
            trashBin: (func='', cls='', addition='', dir="left") => `
                <span class="icon-wrapper ${cls}" onclick="${func}" ${addition} desc="wrapper trash bin ${dir}">
                    <svg class="icon trash-bin-container ${dir}" viewBox="0 0 24 24" xmlns="w3.org" desc="trash bin ${dir}">
                        <path class="trash-bin-lid" d="M3 7H21M9 7V5C9 3.8954 9.8954 3 11 3H13C14.1046 3 15 3.8954 15 5V7" desc="trash bin lid"></path>
                        <path class="trash-bin-body" d="M5 7 6 17C6.4 21 7 21 9 21H15C17 21 17.6 21 18 17L19 7" desc="trash bin body"></path>
                        <path class="trash-bin-body" d="M9.5 10 10 17" desc="trash bin left line"></path>
                        <path class="trash-bin-body" d="M14.5 10 14 17" desc="trash bin right line"></path>
                    </svg>
                </span>
            `,
            save: (func='', cls='', addition='') => `
                <span class="icon-wrapper ${cls}" onclick="${func}" ${addition} desc="wrapper floppy disk">
                    <svg class="icon floppy-disk-container" id="floppyDiskContainer" viewBox="0 0 24 24" xmlns="w3.org" desc="floppy disk">
                        <path d="M19 21H5C4 21 3 20 3 19V6l3-3H19C20 3 21 4 21 5V19C21 20 20 21 19 21Z" desc="floppy disk body"/>
                        <path class="floppy-disk-slider" d="M9 3V8H15V3" fill="var(--primary-color)" desc="floppy disk top"/>
                        <path d="M7 21V13H17V21" desc="floppy disk bottom"/>
                    </svg>
                </span>
            `,
            arrow: (func='', cls='', addition='', dir="up") => `
                <span class="icon-wrapper ${cls}" onclick="${func}" ${addition} desc="wrapper arrow ${dir}">
                    <svg class="icon arrow-container ${dir}" viewBox="0 0 24 24" xmlns="w3.org" desc="arrow ${dir}">
                        <path class="arrow-body" d="M3 18 12 6 21 18Z" desc="arrow body ${dir}"/>
                        <path class="arrow-line" d="M6 18H18" desc="arrow line ${dir}"/>
                    </svg>
                </span>
            `,
            pin: (func='', cls='', addition='', state="pin") => `
                <span class="icon-wrapper ${cls}" onclick="${func}" ${addition} desc="wrapper pin">
                    <svg class="icon pin-container ${state}" viewBox="0 0 24 24" xmlns="w3.org" desc="pin">
                        <path d="M15 4C13 2 13 7 12 8 11 9 4 9 6 11L13 18C15 20 15 13 16 12 17 11 22 11 20 9L15 4" desc="pin body"/>
                        <path d="M3 21 9.5 14.5" desc="pin needle"/>
                        ${state == "pin" ? '' : '<path class="pin-not" d="M3 3 21 21" desc="pin not"/>'}
                    </svg>
                </span>
            `,
            tick: (func='', cls='', addition='') => `
                <span class="icon-wrapper ${cls}" onclick="${func}" ${addition} desc="wrapper tick">
                    <svg class="icon tick-container" viewBox="0 0 24 24" xmlns="w3.org" desc="tick">
                        <path d="M16 4.5 12 16.5C11.6666 17.5 11.5 17.5 10 15.5L7 11.5C6.25 10.5 6 10.5 5 11.5L4 12.5C3 13.5 3 13.5 4 14.5L9 19.5C11 21.5 12 22.5 14 18.5L20 6.5C21 4.5 21 4.5 19 3.5 17 2.5 17 1.5 16 4.5" desc="tick body"/>
                    </svg>
                </span>
            `,
            cross: (func='', cls='', addition='') => `
                <span class="icon-wrapper ${cls}" onclick="${func}" ${addition} desc="wrapper cross">
                    <svg class="icon cross-container" viewBox="0 0 24 24" xmlns="w3.org" desc="cross">
                        <path d="M17 4C19 2 22 5 20 7L16 11C15 12 15 12 16 13L20 17C22 19 19 22 17 20L13 16C12 15 12 15 11 16L7 20C5 22 2 19 4 17L8 13C9 12 9 12 8 11L4 7C2 5 5 2 7 4L11 8C12 9 12 9 13 8L17 4Z" desc="cross body"/>
                    </svg>
                </span>
            `,
            question: (func='', cls='', addition='') => `
                <span class="icon-wrapper ${cls}" onclick="${func}" ${addition} desc="wrapper question">
                    <svg class="icon question-container" viewBox="0 0 24 24" xmlns="w3.org" desc="question">
                        <path d="M13.2689 15.0309C13.2689 14.1328 13.9504 13.8133 14.894 13.1611L16.0441 12.3731C17.6996 11.2317 18.8215 9.7109 18.8215 7.5652 18.8215 4.8236 16.5497 2.1603 12.2014 2.1603 8.0491 2.1603 5.777 4.9855 5.777 7.9183 5.777 8.0271 5.7846 8.1629 5.7989 8.3238A.9783.9783 90 006.7772 9.2152H8.5327C8.9783 9.2152 9.3394 8.8533 9.3394 8.4076 9.3394 6.8857 10.209 5.3378 12.2015 5.3378 14.0811 5.3378 15.006 6.5335 15.006 7.7837 15.006 8.5979 14.6419 9.3316 13.7995 9.9284L12.4536 10.9067C10.8547 12.0742 10.2372 13.4058 10.2372 14.8451 10.2372 14.9017 10.2394 14.9613 10.2427 15.0267A.9783.9783 90 0011.2167 15.9583H12.3419A.9272.9272 90 0013.2691 15.0311Z" desc="question body"/>
                        <path d="M9.8117 20.5282C9.8117 21.6498 10.735 22.543 11.8937 22.543 13.0536 22.543 14.0017 21.6497 14.0017 20.5282 14.0017 19.4053 13.0536 18.487 11.8937 18.487 10.735 18.487 9.8131 19.4053 9.8131 20.5282Z" desc="question dot"/>
                    </svg>
                </span>
            `,
            pencil: (func='', cls='', addition='') => `
                <span class="icon-wrapper ${cls}" onclick="${func}" ${addition} desc="wrapper pencil">
                    <svg class="icon pencil-container" viewBox="0 0 24 24" xmlns="w3.org" desc="pencil">
                        <path class="pencil-ready" d="M4 21 11 19 21 9C21 9 22.5 7.5 21 6L19 4C17.5 2.5 16 4 16 4L6 14 4 21" desc="pencil body"/>
                        <path class="pencil-ready" d="M14 6 19 11" desc="pencil eraser"/>
                        <path class="pencil-ready" d="M6 14 11 19" desc="pencil head"/>
                        <path class="pencil-paper" d="M2 21 19 21" desc="pencil underline"/>
                    </svg>
                </span>
            `,
            reset: (func='', cls='', addition='') => `
                <span class="icon-wrapper ${cls}" onclick="${func}" ${addition} desc="wrapper reset">
                    <svg class="icon reset-container" viewBox="0 0 24 24" xmlns="w3.org" desc="reset">
                        <path d="M4 17C6.5 21.3301 11.9641 22.7942 16.2942 20.2942 20.6243 17.7942 22.0884 12.3301 19.5884 8 17.0884 3.6699 11.6243 2.2058 7.2942 4.7058" desc="reset curve"/>
                        <path d="M3 7.2058 8.7942 7.3038 5.7942 2.1077Z" desc="reset arrow"/>
                    </svg>
                </span>
            `,
            linkArrow: (func='', cls='', addition='') => `
                <span class="icon-wrapper ${cls}" onclick="${func}" ${addition} desc="wrapper link arrow">
                    <svg class="icon link-arrow-container" viewBox="0 0 24 24" xmlns="w3.org" desc="link arrow">
                        <path d="M18 4C19 4 20 5 20 6L20 16C20 18 16 18 16 16L17 9 7 20C5 22 2 19 4 17L15 7 8 8C6 8 6 4 8 4L18 4Z" desc="link arrow body"/>
                    </svg>
                </span>
            `, 
            // M15.2 3.175C19.7 2.05 21.95 4.3 20.825 8.8L18.575 17.8C17.45 22.3 15.325 22.3 15.325 17.8 15.325 12.175 20.825 4.3 16.325 9.925L11.825 15.55C4 25.3313-1.625 20.235 8.45 12.175L14.075 7.675C19.7 3.175 11.825 8.675 6.2 8.675 1.7 8.675 1.7 6.55 6.2 5.425L15.2 3.175Z
            texts: {
                syn: (func='', cls='', addition='', state="do") => `
                    <span class="icon-wrapper ${cls}" onclick="${func}" ${addition} desc="wrapper syn">
                        <svg class="icon syn-container ${state}" viewBox="0 0 48 24" xmlns="w3.org" desc="syn">
                            <path class="syn-s" d="M16.5 9C16.5 7.5 15 6 12 6 9 6 7.5 7.5 7.5 9 7.5 12 16.5 10.5 16.5 14.25 16.5 16.5 15 18 12 18 9 18 7.5 16.5 7.5 14.25" desc="s"/>
                            <path class="syn-y" d="M19.5 6 24 15M28.5 6 24 15C22.5 18 21 19.5 18 19.5" desc="y"/>
                            <path class="syn-n" d="M31.5 18V6M31.5 10.5C31.5 7.5 33 6 36 6 39 6 40.5 6.75 40.5 10.5V18" desc="n"/>
                            ${state == "do" ? '' : '<path class="syn-not" d="M3 12H45" desc="syn not"/>'}
                        </svg>
                    </span>
                `,
            }
        }

        // Header
        elements.healthIndicator = byId('healthIndicator');
        elements.quickSearchInput = byId('quickSearchInput');
        elements.quickSearchLimit = byId('quickSearchLimit');
        elements.quickSearchThreshold = byId('quickSearchThreshold');
        elements.quickSearchBtn = byId('quickSearchBtn');

        // Sidebar
        elements.sidebar = document.querySelector(".sidebar");

        // Search page
        elements.searchQuery = byId('searchQuery');
        elements.searchLimit = byId('searchLimit');
        elements.searchThreshold = byId('searchThreshold');
        elements.searchBtn = byId('searchBtn');
        elements.searchResults = byId('searchResults');

        // Index page
        elements.reindexData = byId('reindexData');
        elements.reindexMode = byId('reindexMode');
        elements.reindexActivate = byId('reindexActivate');
        elements.reindexPin = byId('reindexPin');
        elements.reindexLlm = byId('reindexLlm');
        elements.reindexBtn = byId('reindexBtn');

        // File reindex page
        elements.fileInput = byId('fileInput');
        elements.fileInputList = byId('fileInputList');
        elements.fileIndexMode = byId('fileIndexMode');
        elements.fileIndexActivate = byId('fileIndexActivate');
        elements.fileIndexPin = byId('fileIndexPin');
        elements.fileIndexLlm = byId('fileIndexLlm');
        elements.fileIndexBtn = byId('fileIndexBtn');

        // Versions page
        elements.refreshVersionsBtn = byId('refreshVersionsBtn');
        elements.versionsNoteTotal = byId('versionsNoteTotal');
        elements.versionsNotePin = byId('versionsNotePin');
        elements.versionsList = byId('versionsList');

        // Articles page
        elements.pageArticlesHeader = byId('pageArticlesHeader');
        elements.pageArticlesHeaderVersionName = byId('pageArticlesHeaderVersionName');
        elements.pageArticlesHeaderVersionRename = byId('pageArticlesHeaderVersionRename');
        elements.backToVersionsBtn = byId('backToVersionsBtn');
        elements.updateArticlesPageBtn = byId('updateArticlesPageBtn');
        elements.versionDetail = byId('versionDetail');
        elements.articlesNoteSort = byId('articlesNoteSort');
        elements.articlesList = byId('articlesList');

        // Article detail page
        elements.articleDetailTitle = byId('articleDetailTitle');
        elements.articleDetailId = byId('articleDetailId');
        elements.backToArticlesBtn = byId('backToArticlesBtn');
        elements.updateArticlePageBtn = byId('updateArticlePageBtn');
        elements.saveAddedSamplesBtn = byId('saveAddedSamplesBtn');
        elements.articleDetailNote = byId('articleDetailNote');
        elements.articleDetailSamples = byId('articleDetailSamples');
        elements.articleDetailSynonyms = byId('articleDetailSynonyms');
        elements.addSampleContainer = `
            <div class="intent-item add">
                <input type="search" class="intent-text" oninput="checkInputTypeSearch(this)" onkeydown="newSampleEnterSave(event)" placeholder="Введите пример вопроса">
                <div class="intent-item-controls">
                    ${elements.icons.save(`saveAddedSample(event)`, "intent-item-control", 'title="Сохранить черновик примера"')}
                </div>
            </div>
        `;
        
        // Database page
        elements.getDatabaseBtn = byId('getDatabaseBtn');
        elements.saveDatabaseBtn = byId('saveDatabaseBtn');
        elements.databaseContainer = byId('databaseContainer');

        // Queue page
        elements.refreshTasksBtn = byId('refreshTasksBtn');
        elements.activeTasks = byId('activeTasks');
        elements.queuedTasks = byId('queuedTasks');
        elements.failedTasks = byId('failedTasks');
        elements.doneTasks = byId('doneTasks');

        // Task detail page
        elements.taskDetailId = byId('taskDetailId');
        elements.backToQueueBtn = byId('backToQueueBtn');
        elements.taskDetail = byId('taskDetail');

        // Stop-words page
        elements.getStopWordsBtn = byId('getStopWordsBtn');
        elements.saveStopWordsBtn = byId('saveStopWordsBtn');
        elements.stopWordsNoteTotal = byId('stopWordsNoteTotal');
        elements.stopWordsList = byId('stopWordsList');
        elements.addStopWordContainer = `
            <div class="stop-word add">
                <input type="search" oninput="checkInputTypeSearch(this)" onkeydown="newStopWordEnterSave(event)" placeholder="Введите стоп-слово">
                ${elements.icons.save(`saveStopWord(event)`, "stop-word-btn", 'title="Сохранить"')}
            </div>
        `;

        // LLM page
        elements.loadLlmConfigBtn = byId('loadLlmConfigBtn');
        elements.saveLlmConfigBtn = byId('saveLlmConfigBtn');
        elements.llmUrl = byId('llmUrl');
        elements.llmModel = byId('llmModel');
        elements.llmTemperature = byId('llmTemperature');
        elements.llmTopP = byId('llmTopP');
        elements.llmFrequencyPenalty = byId('llmFrequencyPenalty');
        elements.llmRepeatPenalty = byId('llmRepeatPenalty');
        elements.llmPresencePenalty = byId('llmPresencePenalty');
        elements.llmPrompt = byId('llmPrompt');


        // Tooltip
        elements.tooltipJson = byId('tooltipJson');
        elements.tooltipXlsx = byId('tooltipXlsx');
        elements.tooltipTxt = byId('tooltipTxt');
        elements.tooltipJsonTxt = byId('tooltipJsonTxt');

        // Spinner
        elements.spinner = (msg) => `<div class="loading"><span class="spinner"></span> ${msg}</div>`;

        // Error
        elements.error = (msg) => `<div class="result-message error">Ошибка: ${msg}</div>`;
    }

    // Setup event listeners
    function setupEventListeners() {
        // Navigation
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (event) => {
                event.preventDefault();
                const page = link.dataset.page;
                showPage(page);
            });
        });

        // Quick search
        elements.quickSearchBtn.addEventListener('click', performQuickSearch);
        elements.quickSearchInput.addEventListener('keypress', (event) => {
            if (event.key === 'Enter') performQuickSearch();
        });

        // Search page
        elements.searchQuery.addEventListener('keypress', performSearchQuery);
        elements.searchLimit.addEventListener('keypress', performSearchQuery);
        elements.searchThreshold.addEventListener('keypress', performSearchQuery);
        elements.searchBtn.addEventListener('click', performSearch);

        // Index page
        elements.reindexBtn.addEventListener('click', performIndex);

        // File reindex page
        elements.fileInput.addEventListener('change', fileInputChange)
        elements.fileIndexBtn.addEventListener('click', performFileIndex);

        // Versions page
        elements.refreshVersionsBtn.addEventListener('click', loadVersions);

        // Version page (Articles page)
        elements.backToVersionsBtn.addEventListener('click', (event) => {
            const element = event.currentTarget;
            showPage('versions');
            element.removeAttribute("version-name");
            element.removeAttribute("version-id");
        });
        elements.updateArticlesPageBtn.addEventListener('click', updateArticlesPageFunction);
        
        // Article page
        elements.backToArticlesBtn.addEventListener('click', (event) => {
            const element = event.currentTarget;
            showPage('articles', element.getAttribute("version-id"));
            element.removeAttribute("version-id");
        });
        elements.updateArticlePageBtn.addEventListener('click', updateArticlePageFunction);
        elements.saveAddedSamplesBtn.addEventListener('click', saveAddedSamplesFunction);

        // Queue page
        elements.refreshTasksBtn.addEventListener('click', loadTasksStatus);
        elements.backToQueueBtn.addEventListener('click', () => showPage('queue'));

        // Stop-words page
        elements.getStopWordsBtn.addEventListener('click', loadStopWords)
        elements.saveStopWordsBtn.addEventListener('click', saveStopWords)

        // LLM page
        elements.loadLlmConfigBtn.addEventListener('click', loadLlmConfig);
        elements.saveLlmConfigBtn.addEventListener('click', saveLlmConfig);

        // Tooltip
        elements.tooltipJson.addEventListener('mouseenter', tooltipMouseEnter);
        elements.tooltipXlsx.addEventListener('mouseenter', tooltipMouseEnter);
        elements.tooltipTxt.addEventListener('mouseenter', tooltipMouseEnter);
        elements.tooltipJson.addEventListener('mouseleave', tooltipMouseLeave);
        elements.tooltipXlsx.addEventListener('mouseleave', tooltipMouseLeave);
        elements.tooltipTxt.addEventListener('mouseleave', tooltipMouseLeave);
    }

    // Show page
    function showPage(pageName, versionId) {
        // Hide all pages
        document.querySelectorAll('.page').forEach(page => {
            page.classList.remove('active');
        });

        // Remove active class from nav links
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });

        // Show selected page
        const page = byId(`page-${pageName}`);
        if (page) {
            page.classList.add('active');
        }

        // Set active nav link
        const navLink = document.querySelector(`.nav-link[data-page="${pageName}"]`);
        if (navLink) {
            navLink.classList.add('active');
        }

        // Load data for specific pages
        switch (pageName) {
            case "search":
                elements.searchResults.hidden = true;
                break;
            case "reindex":
                insertPlaceholder([elements.reindexData], [elements.tooltipJsonTxt.firstElementChild]);
                break;
            case "reindex-file":
                insertPlaceholder([], [elements.tooltipJson.firstElementChild, elements.tooltipTxt.firstElementChild]);
                break;
            case "versions":
                loadVersions();
                break;
            case "articles":
                loadVersion(versionId);
                break;
            case "database":
                loadDatabase();
                break;
            case "queue":
                loadTasksStatus();
                break;
            case "stop-words":
                loadStopWords();
                break;
            case "llm":
                loadLlmConfig();
                break;
        }
    }

    // Health check
    async function checkHealth() {
        try {
            const response = await fetch(`${API_BASE}/health`);
            const data = await response.json();

            elements.healthIndicator.className = 'health-indicator';
            elements.healthIndicator.querySelector('.status-dot').className = 'status-dot online';
            elements.healthIndicator.querySelector('.status-text').textContent = 'Доступен';
            elements.quickSearchBtn.classList.add("online");
        } catch (error) {
            elements.healthIndicator.className = 'health-indicator';
            elements.healthIndicator.querySelector('.status-dot').className = 'status-dot offline';
            elements.healthIndicator.querySelector('.status-text').textContent = 'Недоступен';
            elements.quickSearchBtn.classList.remove("offline");
        }
    }

    // Health chech cycle
    function startHealthCheck() {
        checkHealth();
        healthCheckInterval = setInterval(checkHealth, 30000);
    }

    // Quick search from header
    async function performQuickSearch() {
        const query = elements.quickSearchInput.value.trim();
        const limit = parseInt(elements.quickSearchLimit.value) || 10;
        const threshold = parseFloat(elements.quickSearchThreshold.value) || 0.7;

        if (!query) {
            showToast('Введите вопрос для поиска', 'error');
            return;
        }

        showPage('search');
        elements.searchQuery.value = query;
        elements.searchLimit.value = limit;
        elements.searchThreshold.value = threshold;
        await performSearch();
    }

    // Hot search
    function performSearchQuery(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            performSearch();
        }
    }

    // Search
    async function performSearch() {
        const query = elements.searchQuery.value.trim();
        const limit = parseInt(elements.searchLimit.value) || 10;
        let threshold = parseFloat(elements.searchThreshold.value);
        threshold = threshold || threshold == 0 ? threshold : 0.7

        if (!query) {
            showToast('Введите вопрос для поиска', 'error');
            return;
        }

        setLoading(elements.quickSearchBtn);
        setLoading(elements.searchBtn);

        try {
            const url = `${API_BASE}/search?limit=${limit}&threshold=${threshold}`
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ query })
            });

            const data = await response.json();
            checkResponse(response, data);

            displaySearchResults(data);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error')
        } finally {
            resetLoading(elements.quickSearchBtn);
            resetLoading(elements.searchBtn);
        }
    }

    // Display search results
    function displaySearchResults(data) {
        const resultMetaElement = elements.searchResults.querySelector(".result-meta");
        const resultListElement = elements.searchResults.querySelector(".result-list");

        resultMetaElement.innerHTML = `
            <p>
                <span>Версия: ${escapeHtml(data.version_used || 'N/A')}</span>
                ${elements.icons.linkArrow(`showVersionDetailPage('${data.version_used}')`, '', 'title="Открыть версию"')}
            </p>
            <p>Время обработки: ${data.processing_time_ms?.toFixed(2) || 'N/A'} мс</p>
        `;

        if (!data.articles || data.articles.length === 0) {
            resultListElement.innerHTML = '<div class="result-list-item zero"><p>Ничего похожего не найдено</p></div>';
            showToast("Попробуйте задать другой вопрос или снизить порог схожести", 'info');
            return;
        }
        
        let html = '';
        data.articles.forEach((article, index) => {
            const score = data.scores?.[index] || 0;
            html += `
                <div class="result-list-item">
                    ${elements.icons.linkArrow(`showArticleDetail('${data.version_used}', '${article}')`, '', 'title="Открыть статью"')}
                    <h4>${escapeHtml(article)}</h4>
                    <span>${score.toFixed(6)}</span>
                </div>
            `;
        });

        resultListElement.innerHTML = html;
        elements.searchResults.removeAttribute("hidden");
    }

    // Index (manual JSON input)
    async function performIndex() {
        const dataStr = elements.reindexData.value.trim();

        if (!dataStr) {
            showToast('Введите данные в формате JSON', 'error');
            return;
        }

        let query;
        try {
            query = JSON.parse(dataStr);
        } catch (error) {
            showToast(`Ошибка JSON: ${error.message}`, 'error');
            return;
        }

        const mode = elements.reindexMode.checked;
        const activate = elements.reindexActivate.checked;
        const pin = elements.reindexPin.checked;
        const llm = elements.reindexLlm.checked;

        setLoading(elements.reindexBtn);

        try {
            const url = `${API_BASE}/reindex?update_current=${mode}&activate=${activate}&pin=${pin}&llm=${llm}`
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ data: query })
            });

            const data = await response.json();
            checkResponse(response, data);

            showToast(`Задача создана: ${data.task_id}`, 'info');
            resetIndexPage();
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        } finally {
            resetLoading(elements.reindexBtn);
        }
    }

    // Reset index page
    function resetIndexPage() {
        elements.reindexData.value = '';
        elements.reindexMode.checked = false;
        elements.reindexActivate.checked = false;
        elements.reindexPin.checked = false;
        elements.reindexLlm.checked = false;
    }

    // Added file to input
    function fileInputChange(event) {
        try {
            const element = event.currentTarget;
            elements.fileInputList.innerHTML = '';

            Array.from(element.files).forEach(file => elements.fileInputList.innerHTML += `
                <div class="input-file-list-item">
                    ${elements.icons.trashBin(`removeFilesItem(event)`, '', "input-file-list-remove", "right")}
                    <span class="input-file-list-name">${file.name}</span>
                </div>
            `);

            const filesNumber = element.files.length
            let naming = (a, b) => ["Добавлен" + a, "файл" + b];
            switch (true) {
                case filesNumber == 0 || ["11", "12", "13", "14"].includes(String(filesNumber).slice(-2)):
                    naming = naming('о', "ов");
                    break;
                case filesNumber == 1 || String(filesNumber).slice(-1) == '1':
                    naming = naming('', '');
                    break;
                case [2, 3, 4].includes(filesNumber) || ['2', '3', '4'].includes(String(filesNumber).slice(-1)):
                    naming = naming('о', 'а');
                    break;
                default:
                    naming = naming('о', "ов");
            }
            showToast(naming.toSpliced(1, 0, filesNumber).join(' '), "success");
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        }
    }

    // Delete file to input
    function removeFilesItem(event) {
        try {
            event.preventDefault();
            event.stopPropagation();

            const element = event.currentTarget;
            const name = element.nextElementSibling.textContent;

            const files = new DataTransfer();
            Array.from(elements.fileInput.files).forEach(file => files.items.add(file));

            for (let i = 0; i < files.items.length; i++) {
                if (name === files.items[i].getAsFile().name) {
                    files.items.remove(i);
                    break;
                }
            }
            
            elements.fileInput.files = files.files;
            element.closest('.input-file-list-item').remove();
            
            showToast(`Удален файл ${name}`, 'info');
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        }
    }

    // File reindex
    async function performFileIndex() {
        const files = Array.from(elements.fileInput.files);

        if (!files || !files.length) {
            showToast('Загрузите файл(-ы) для индексации', 'error');
            return;
        }

        const mode = elements.fileIndexMode.checked;
        const activate = elements.fileIndexActivate.checked;
        const pin = elements.fileIndexPin.checked;
        const llm = elements.fileIndexLlm.checked;
        const url = `${API_BASE}/reindex/file?update_current=${mode}&activate=${activate}&pin=${pin}&llm=${llm}`

        const formData = new FormData();
        files.forEach(file => formData.append('files', file));

        setLoading(elements.fileIndexBtn);

        try {
            const response = await fetch(url, {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            checkResponse(response, data);

            showToast(`Задача создана: ${data.task_id}`, 'info');
            resetFileIndexPage();
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        } finally {
            resetLoading(elements.fileIndexBtn);
        }
    }

    // Reset file index page
    function resetFileIndexPage() {
        elements.fileInput.files.value = '';
        elements.fileIndexMode.checked = false;
        elements.fileIndexActivate.checked = false;
        elements.fileIndexPin.checked = false;
        elements.fileIndexLlm.checked = false;
        elements.fileInputList.innerHTML = '';
    }

    // Tasks status
    async function loadTasksStatus() {
        setLoading(elements.refreshTasksBtn);
        
        try {
            const response = await fetch(`${API_BASE}/queue`);
            
            const data = await response.json();
            checkResponse(response, data);
            
            displayTasksStatus(data);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        } finally {
            resetLoading(elements.refreshTasksBtn);
        }
    }

    // Display tasks status
    function displayTasksStatus(data) {
        // Mapping
        const keyMapping = {
            "active_tasks": [
                "activeTasks",
                "Активная задача"
            ],
            "queued_tasks": [
                "queuedTasks",
                "Задачи в очереди"
            ],
            "failed_tasks": [
                "failedTasks",
                "Проваленные задачи"
            ],
            "done_tasks": [
                "doneTasks",
                "Завершенные задачи"
            ],
        };
        const stepMapping = {
            "starting": "Старт процесса",
            "saving_db": "Сохранение в БД",
            "generating_embeddings": "Генерация эмбеддингов",
            "generating_synonyms": "Генерация синонимов",
            "completed": "Завершен",
        };

        // Display tasks
        for (const [key, tasks] of Object.entries(data)) {
            const tasksLen = tasks.length;
            const [type, headerTxt] = keyMapping[key];
            const headerHtml = `
                <div class="tasks-data-section-header accordion-header">
                    <h3>${headerTxt} (${tasksLen})</h3>
                    <div class="section-header-controls">
                        ${elements.icons.arrow(`toggleAccordion(event, 'section-header-control', false)`, "section-header-control", 'title="Свернуть"')}
                    </div>
                </div>
            `;

            const taskTypeMapping = {
                "s-syn": "Сохранение синонимов",
                "d-art": "Удаление статьи",
                "d-eos": "Удаление примеров и/или синонимов",
                "d-syn": "Удаление синонимов",
                "d-eas": "Удаление примеров и синонимов",
                "c-syn": "Генерация синонимов",
                "c-idx": "Индексация",
                get(val='') { return this[val.slice(0, val.indexOf('_'))] || "Неизвестно" }
            }
            const calcPercent = (a, b) => (Number.isFinite(a) && Number.isFinite(b) && b !== 0) ? (a * 100 / b).toFixed(2) : 0;
            let contentHtml = `<div class="tasks-data-section-list accordion-content" id="${type}SectionList">`;
            tasks.forEach(task => {
                const progressPercent = calcPercent(task.progress?.current, task.progress?.total) + '%';
                const typeShort = type.replace("Tasks", '');
                contentHtml += `
                    <div class="task-item" onclick="showTaskDetail('${task.task_id}', '${typeShort}')" name="${task.task_id}">
                        <div class="task-item-column">
                            <p><strong>ID:</strong><span>${task.task_id || '-'}</span></p>
                            <p><strong>Создана:</strong><span>${fromIsoTimeFormat(task.queued_at) || '-'}</span></p>
                            <p><strong>Начата:</strong><span>${fromIsoTimeFormat(task.started_at) || '-'}</span></p>
                            <p><strong>Завершена:</strong><span>${fromIsoTimeFormat(task.completed_at) || '-'}</span></p>
                        </div>
                        <div class="task-item-column">
                            <p><strong>Тип:</strong><span>${taskTypeMapping.get(task.task_id) || '-'}</span></p>
                            <p><strong>Записей:</strong><span>${task.progress?.total || '-'}</span></p>
                            <p><strong>Этап:</strong><span>${stepMapping[task.progress?.step] || '-'}</span></p>
                            <p><strong>Ошибка:</strong><span>${task.error || '-'}</span></p>
                        </div>
                        <div class="task-item-controls">
                            ${task.parameters?.article_id
                                ? elements.icons.linkArrow(`showArticleDetail('${task.parameters.version_id}', '${task.parameters.article_id}', event)`, "task-item-control", 'title="Перейти к статье"')
                                : task.parameters?.version_id
                                    ? elements.icons.linkArrow(`showVersionDetailPage('${task.parameters.version_id}', event)`, "task-item-control", 'title="Перейти к версии"')
                                    : ''
                            }
                            ${elements.icons.trashBin(`deleteQueueTask('${task.task_id}', event)`, "task-item-control", 'title="Удалить"')}
                        </div>
                        <div class="task-item-progress-bar ${typeShort}" style="--progress: ${progressPercent};"
                            data-text="${progressPercent}">${progressPercent}</div>
                    </div>
                `;
            });

            if (!tasksLen) contentHtml += '<div class="task-item zero">Нет задач</div>';
            contentHtml += `</div>`;
            elements[type].innerHTML = headerHtml + contentHtml;

            // Сворачиваем все секции без задач
            const arrowIcon = elements[type].querySelector('.section-header-controls .icon-wrapper[desc*="arrow"]');
            if (arrowIcon) toggleAccordion({ stopPropagation: () => {}, currentTarget: arrowIcon }, "section-header-control", tasksLen);
        }
    }

    async function deleteQueueTask(taskId, event) {
        event.stopPropagation();
        if (!await showConfirm(`Вы уверены, что хотите удалить задачу ${taskId}?`))
            return;

        try {
            const response = await fetch(
                `${API_BASE}/task/${taskId}`,
                { method: 'DELETE' }
            );

            const data = await response.json();
            checkResponse(response, data);

            showToast(`Задача ${taskId} удалена`, 'success');
            displayTasksStatus(data.data);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        }
    }

    // Task detail
    async function showTaskDetail(taskId, taskType) {
        showPage('task-detail');
        elements.taskDetailId.textContent = taskId;
        setLoading(elements.backToQueueBtn);

        try {
            const response = await fetch(`${API_BASE}/task/${taskId}`);

            const data = await response.json();
            checkResponse(response, data);

            displayTaskDetail(data, taskType);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        } finally {
            resetLoading(elements.backToQueueBtn);
        }
    }

    // Display task detail
    function displayTaskDetail(task, type) {
        elements.taskDetail.innerHTML = '';

        const calcPercent = (a, b) => (Number.isFinite(a) && Number.isFinite(b) && b !== 0) ? (a * 100 / b).toFixed(2) : 0;
        const progressPercent = calcPercent(task.progress?.current, task.progress?.total) + '%';
        const stepMapping = {
            "starting": "Старт процесса",
            "saving_db": "Сохранение в БД",
            "generating_embeddings": "Генерация эмбеддингов",
            "generating_synonyms": "Генерация синонимов",
            "completed": "Завершен",
        };
        const tickCrossQuestion = (val, cls) => elements.icons[val === true ? "tick" : val === false ? "cross" : "question"](``, cls);

        const html = `
            <div class="task-detail-data">
                <div class="task-detail-data-column main">
                    <p><strong>ID:</strong><span>${task.task_id || '-'}</span></p>
                    <p><strong>Создана:</strong><span>${fromIsoTimeFormat(task.queued_at) || '-'}</span></p>
                    <p><strong>Начата:</strong><span>${fromIsoTimeFormat(task.started_at) || '-'}</span></p>
                    <p><strong>Завершена:</strong><span>${fromIsoTimeFormat(task.completed_at) || '-'}</span></p>
                    <p><strong>Записей:</strong><span>${task.progress?.total || '-'}</span></p>
                    <p><strong>Этап:</strong><span>${stepMapping[task.progress?.step] || '-'}</span></p>
                    <p><strong>Ошибка:</strong><span>${task.error || '-'}</span></p>
                </div>
                <div class="task-detail-data-column additional">
                    <p>${tickCrossQuestion(task.parameters?.update_current, "task-detail-data-param")}<strong>Добавить к активной версии</strong></p>
                    <p>${tickCrossQuestion(task.parameters?.activate, "task-detail-data-param")}<strong>Сделать версию активной</strong></p>
                    <p>${tickCrossQuestion(task.parameters?.pin, "task-detail-data-param")}<strong>Закрепить версию</strong></p>
                    <p>${tickCrossQuestion(task.parameters?.llm, "task-detail-data-param")}<strong>Дозапросить синонимы у LLM</strong></p>
                </div>
                <div class="task-item-controls">
                    ${task.parameters?.article_id
                        ? elements.icons.linkArrow(`showArticleDetail('${task.parameters.version_id}', '${task.parameters.article_id}')`, "task-item-control", 'title="Перейти к статье"')
                        : task.parameters?.version_id
                            ? elements.icons.linkArrow(`showVersionDetailPage('${task.parameters.version_id}')`, "task-item-control", 'title="Перейти к версии"')
                            : ''
                    }
                    ${elements.icons.trashBin(`deleteQueueTask('${task.task_id}', event); showPage('queue');`, "task-item-control", 'title="Удалить"')}
                </div>
            </div>
            <div class="task-item-progress-bar ${type}" style="--progress: ${progressPercent};"
                data-text="${progressPercent}">${progressPercent}</div>
        `;

        elements.taskDetail.innerHTML = html;
    }

    // Insert JSON placeholder
    function insertPlaceholder(placeholders=[], innerHtmls=[]) {
        placeholders.forEach(element => element.placeholder = indexJsonPlaceholder);
        innerHtmls.forEach(element => element.innerHTML = indexJsonPlaceholder);
    }

    // Versions
    async function loadVersions() {
        setLoading(elements.refreshVersionsBtn);

        try {
            const response = await fetch(`${API_BASE}/versions`);

            const data = await response.json();
            checkResponse(response, data);

            displayVersions(data);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        } finally {
            resetLoading(elements.refreshVersionsBtn);
        }
    }

    function displayVersions(data) {
        if (!data.versions || data.versions.length === 0) {
            elements.versionsNoteTotal.textContent = 0;
            elements.versionsNotePin.hidden = true;
            elements.versionsList.innerHTML = `<div class="version-item zero"><div class="version-info"><p>Нет версий</p></div></div>`;
            return;
        }

        elements.versionsNoteTotal.textContent = data.total_versions;
        elements.versionsNotePin.textContent = data.pin_versions;
        
        let html = "";
        data.versions.forEach(({ version_name, version_id, is_active, is_pin, created_at, articles_count, vectors_count }) => {
            if (is_active) activeVersionId = version_id;
            html += `
                <div class="version-item clickable ${is_active ? "active" : ''}" onclick="showVersionDetailPage('${escapeHtml(version_id)}')">
                    <div class="version-info">
                        <p class="version-info-name">
                            <strong class="version-info-name-strong">${escapeHtml(version_name)}</strong>
                            <span class="version-info-rename">
                                ${elements.icons.pencil(`renameVersionEvent('${version_name}', '${version_id}', event)`, '', 'title="Переименовать"')}
                            </span>
                        </p>
                        <p>ID: ${escapeHtml(version_id)}</p>
                        <p>Создана: ${escapeHtml(fromIsoTimeFormat(created_at))}</p>
                        <p>Статей: ${articles_count}, Векторов: ${vectors_count}</p>
                    </div>
                    <div class="version-actions">
                        ${is_active ? '' : elements.icons.tick(
                            `activateVersion('${escapeHtml(version_id)}', 'loadVersions', event)`,
                            "version-action", 'title="Активировать"'
                        )}
                        ${elements.icons.pin(
                            `${is_pin ? "unpinVersion" : "pinVersion"}('${escapeHtml(version_id)}', 'loadVersions', event)`, 
                            "version-action", `title="${is_pin ? "Открепить" : "Закрепить"}"`, is_pin ? "unpin" : "pin"
                        )}
                        ${(is_active || is_pin) ? '' : elements.icons.trashBin(
                            `deleteVersion('${escapeHtml(version_id)}', 'loadVersions', '${escapeHtml(version_name)}', event)`,
                            "version-action", 'title="Удалить"', "left"
                        )}
                    </div>
                </div>
            `;
        });

        elements.versionsList.innerHTML = html;
    }

    // Version rename - stop propogation
    function renameVersionStopPropagation(event) {
        event.stopPropagation()
    }

    // Version save - caused by 'Enter'
    function renameVersionEnterSave(event) {
        event.preventDefault();
        const text = event.clipboardData.getData('text/plain').replace(/[\r\n]+/g, " ");
        const selection = window.getSelection();
        if (!selection.rangeCount) return;
        selection.deleteFromDocument();
        selection.getRangeAt(0).insertNode(document.createTextNode(text));
        selection.collapseToEnd();
    }

    // Version rename
    function renameVersionEvent(versionName, versionId, event) {
        event.stopPropagation();
        const commonParent = event.currentTarget.closest(".version-info-name");

        const versionNameElement = commonParent.firstElementChild;
        versionNameElement.setAttribute("contenteditable", "true");
        versionNameElement.classList.add("rename");
        versionNameElement.addEventListener('click', renameVersionStopPropagation);
        versionNameElement.addEventListener('paste', renameVersionEnterSave);
        versionNameElement.addEventListener('keydown', (keydownEvent) => {
            if (keydownEvent.key === 'Enter') {
                keydownEvent.preventDefault();
                keydownEvent.target.blur();
                saveVersionName(versionName, versionId, keydownEvent);
            }
        });

        // Фокусировка с выделением всего текста
        versionNameElement.focus();
        window.getSelection().selectAllChildren(versionNameElement);

        const controlParent = commonParent.lastElementChild;
        controlParent.innerHTML = (
            elements.icons.save(`saveVersionName('${versionName}', '${versionId}', event)`, '', 'title="Сохранить"') + 
            elements.icons.reset(`resetVersionName('${versionName}', '${versionId}', event)`, '', 'title="Сбросить"')
        );
    }

    function saveVersionName(origVersionName, versionId, event) {
        event.stopPropagation();

        const commonParent = event.currentTarget.closest(".version-info-name");
        const versionNameElement = commonParent.firstElementChild;
        const controlParent = commonParent.lastElementChild;
        const newVersionName = versionNameElement.textContent.trim();

        if (!newVersionName) {
            showToast("Введите название версии", "error");
            return;
        }

        controlParent.innerHTML = elements.icons.pencil(`renameVersionEvent('${origVersionName}', '${versionId}', event)`, '', 'title="Переименовать"');
        versionNameElement.classList.remove("rename");
        versionNameElement.removeAttribute("contenteditable");
        versionNameElement.removeEventListener('click', renameVersionStopPropagation);

        if (newVersionName == origVersionName) {
            showToast("Название версии сохранено", "success");
            return;
        }

        versionNameElement.removeEventListener('paste', renameVersionEnterSave);
        renameVersion(versionId, "loadVersions", newVersionName, event);
    }

    async function resetVersionName(origVersionName, versionId, event) {
        event.stopPropagation();
        const commonParent = event.currentTarget.parentElement.parentElement;

        const controlParent = commonParent.getElementsByTagName("span")[0];
        controlParent.innerHTML = elements.icons.pencil(`renameVersionEvent('${origVersionName}', '${versionId}', event)`, '', 'title="Переименовать"');

        const versionNameElement = commonParent.getElementsByTagName("strong")[0];
        versionNameElement.classList.remove("rename");
        versionNameElement.removeAttribute("contenteditable");
        versionNameElement.removeEventListener('click', renameVersionStopPropagation);
        versionNameElement.removeEventListener('paste', renameVersionEnterSave);
        versionNameElement.textContent = origVersionName;
    }

    // Version actions
    async function activateVersion(versionId, nextFunction, event) {
        event.stopPropagation();
        if (versionId == activeVersionId) return;
        await versionAction(versionId, nextFunction, 'activate');
    }

    async function renameVersion(versionId, nextFunction, versionName, event) {
        event.stopPropagation();
        await versionAction(versionId, nextFunction, 'rename', versionName);
    }

    async function pinVersion(versionId, nextFunction, event) {
        event.stopPropagation();
        await versionAction(versionId, nextFunction, 'pin');
    }

    async function unpinVersion(versionId, nextFunction, event) {
        event.stopPropagation();
        await versionAction(versionId, nextFunction, 'unpin');
    }

    async function deleteVersion(versionId, nextFunction, versionName, event) {
        event.stopPropagation();
        if (!await showConfirm(`Удалить версию ${versionName}?`)) return;
        await versionAction(versionId, nextFunction, 'delete');
    }

    // async function doSmthWithVersion(action, ...params) {
    //     const func = action + "Version"
    //     window[func](...params);
    // }

    async function versionAction(versionId, nextFunction, action, name = null) {
        try {
            const url = `${API_BASE}/versions/${versionId}`
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ action, name })
            });

            const data = await response.json();
            checkResponse(response, data);

            const actionDict = {
                "activate": "активирована",
                "rename": "переименована",
                "pin": "закреплена",
                "unpin": "откреплена",
                "delete": "удалена",
            }
            showToast(`Версия ${versionId} ${actionDict[action]}`, 'success')
            window[nextFunction](versionId);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        }
    }

    // Version detail page
    async function showVersionDetailPage(versionId, event) {
        if (event) event.stopPropagation();

        showPage('articles', versionId);
        setLoading(elements.updateArticlesPageBtn);
    }

    // Load version
    function loadVersion(versionId) {
        showVersionDetail(versionId);
        loadArticles(versionId);
    }

    // Update Version detail page
    function updateArticlesPageFunction() {
        setLoading(elements.updateArticlesPageBtn);

        const versionId = byId("versionDetailId").textContent;
        loadVersion(versionId);
    }

    // Version detail
    async function showVersionDetail(versionId) {
        try {
            const response = await fetch(`${API_BASE}/versions`);

            const data = await response.json();
            checkResponse(response, data);

            const version = data.versions.find(v => v.version_id === versionId);
            if (!version) {
                throw new Error('Версия не найдена');
            }

            displayVersionDetail(version);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        } finally {
            resetLoading(elements.updateArticlesPageBtn);
        }
    }

    function displayVersionDetail({ version_name, version_id, created_at, is_active, is_pin, vectors_count, articles_count }) {
        elements.backToVersionsBtn.setAttribute("version-name", version_name);
        elements.backToVersionsBtn.setAttribute("version-id", version_id);
        elements.pageArticlesHeaderVersionName.innerHTML = version_name;
        elements.pageArticlesHeaderVersionRename.innerHTML = elements.icons.pencil(
            `renameVersionEvent('${version_name}', '${version_id}', event)`, 
            '', 'title="Переименовать"'
        );

        let html = `
            <div class="version-info">
                <p><strong>ID:</strong><span id="versionDetailId">${escapeHtml(version_id)}</span></p>
                <p><strong>Создана:</strong>${escapeHtml(fromIsoTimeFormat(created_at))}</p>
                <p><strong>Векторов:</strong>${vectors_count}</p>
                <p><strong>Статей:</strong>${articles_count}</p>
            </div>
            <div class="version-actions">
                ${is_active ? '' : elements.icons.tick(
                    `activateVersion('${escapeHtml(version_id)}', 'showVersionDetailPage', event)`,
                    "version-action", `title="${is_active ? '' : "Активировать"}"`
                )}
                ${elements.icons.pin(
                    `${is_pin ? "unpinVersion" : "pinVersion"}('${escapeHtml(version_id)}', 'showVersionDetailPage', event)`, 
                    "version-action", `title="${is_pin ? "Открепить" : "Закрепить"}"`, is_pin ? "unpin" : "pin"
                )}
                ${is_active || is_pin ? '' : elements.icons.trashBin(
                    `deleteVersion('${escapeHtml(version_id)}', 'showVersionDetailPage', '${escapeHtml(version_name)}', event)`,
                    "version-action", 'title="Удалить"', "left"
                )}
            </div>
        `;

        elements.versionDetail.innerHTML = html;
    }

    // Articles
    async function loadArticles(versionId) {
        try {
            const response = await fetch(`${API_BASE}/articles/${encodeURIComponent(versionId)}`);
            
            const data = await response.json();
            checkResponse(response, data);

            displayArticles(versionId, data);
            currentVersionId = versionId;
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        } finally {
            resetLoading(elements.updateArticlesPageBtn);
        }
    }

    // Display articles
    function displayArticles(versionId, data) {
        if (!data.articles || data.articles.length === 0) {
            elements.articlesNoteSort.hidden = true;
            elements.articlesList.innerHTML = `<div class="article-item zero"><div class="article-item-info"><p>Нет статей</p></div></div>`;
            return;
        }

        elements.articlesNoteSort.hidden = false;
        elements.articlesNoteSort.addEventListener('change', (event) => {
            const element = event.currentTarget;
            const sortType = element.value;
            if (sortType !== 'original') element.querySelector('option[value="original"]')?.remove();
            sortArticlesList(sortType);
        });

        let html = '';
        data.articles.forEach(({ article_id, article_title, samples_count, synonyms_count }) => {
            html += `
                <div class="article-item clickable" onclick="showArticleDetail('${escapeHtml(versionId)}', '${escapeHtml(article_id)}')">
                    <div class="article-item-info">
                        <h3>${escapeHtml(article_title)}</h3>
                        <div class="article-item-info-meta">
                            <p class="clickable-text" onclick="copyToClipboard(this, event)">${escapeHtml(article_id)}</p>
                            <p>Примеров: ${samples_count}, Синонимов: ${synonyms_count}</p>
                        </div>
                    </div>
                    <div class="article-item-controls">
                        ${!synonyms_count ? '' 
                            : elements.icons.texts.syn(`deleteSynonymsForArticle(event, '${article_id}')`, "article-item-control", 'title="Удалить все синонимы"', "undo")
                        }
                        ${!(samples_count || synonyms_count) ? ''
                            : elements.icons.reset(`deleteIntentsForArticle(event, '${article_id}')`, "article-item-control", 'title="Удалить все примеры вопросов и синонимы"')
                        }
                        ${elements.icons.trashBin(`deleteArticle(event, '${article_id}')`, "article-item-control", 'title="Удалить статью"', "left")}
                    </div>
                </div>
            `;
        });

        elements.articlesList.innerHTML = html;
    }

    // Сортировка элементов списка статей
    function sortArticlesList(sortType) {
        const items = Array.from(elements.articlesList.children);
        if (items.length === 0) return;

        const itemsData = items.map(element => ({
            element,
            id: element.querySelector('.clickable-text')?.textContent || '',
            title: element.querySelector('h3')?.textContent || ''
        }));

        itemsData.sort((a, b) => {
            switch (sortType) {
                case 'id-desc':
                    return a.id.localeCompare(b.id);
                case 'id-asc':
                    return b.id.localeCompare(a.id);
                case 'title-desc':
                    return a.title.localeCompare(b.title, 'ru');
                case 'title-asc':
                    return b.title.localeCompare(a.title, 'ru');
                default:
                    return 0;
            }
        });

        elements.articlesList.append(...itemsData.map(el => el.element));
    }

    // Delete all synonyms for article
    async function deleteSynonymsForArticle(event, article_id) {
        event.stopPropagation();
        if (!await showConfirm('Удалить все синонимы для этой статьи?')) return;

        try {
            const versionId = elements.backToVersionsBtn.getAttribute("version-id");
            
            const response = await fetch(
                `${API_BASE}/articles/${encodeURIComponent(versionId)}/${encodeURIComponent(article_id)}/synonyms`,
                { method: 'DELETE' }
            );

            const data = await response.json();
            checkResponse(response, data);

            showToast(`Задача создана: ${data.task_id}`, 'info');
            setTimeout(() => showToast(`Чтобы увидеть изменения, нажмите кнопку "Обновить"`, 'info'), 1000);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        }
    }

    // Delete all samples and synonyms for article
    async function deleteIntentsForArticle(event, article_id) {
        event.stopPropagation()
        if (!await showConfirm('Удалить все примеры вопросов и синонимы для этой статьи?')) return;

        try {
            const versionId = elements.backToVersionsBtn.getAttribute("version-id");

            const response = await fetch(
                `${API_BASE}/articles/${encodeURIComponent(versionId)}/${encodeURIComponent(article_id)}/all`,
                { method: 'DELETE' }
            );

            const data = await response.json();
            checkResponse(response, data);

            showToast(`Задача создана: ${data.task_id}`, 'info');
            setTimeout(() => showToast(`Чтобы увидеть изменения, нажмите кнопку "Обновить"`, 'info'), 1000);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        }
    }

    // Delete article
    async function deleteArticle(event, article_id) {
        event.stopPropagation()
        if (!await showConfirm('Удалить эту статью?')) return;

        try {
            const versionId = elements.backToVersionsBtn.getAttribute("version-id");

            const response = await fetch(
                `${API_BASE}/articles/${encodeURIComponent(versionId)}/${encodeURIComponent(article_id)}`,
                { method: 'DELETE' }
            );

            const data = await response.json();
            checkResponse(response, data);

            showToast(`Задача создана: ${data.task_id}`, 'info');
            setTimeout(() => showToast(`Чтобы увидеть изменения, нажмите кнопку "Обновить"`, 'info'), 1000);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        }
    }

    // Article detail
    async function showArticleDetail(versionId, articleId, event) {
        if (event) event.stopPropagation();

        showPage('article-detail');
        setLoading(elements.updateArticlePageBtn);
        setSpinner(elements.articleDetailSamples, "Загрузка примеров");
        setSpinner(elements.articleDetailSynonyms, "Загрузка синонимов");

        elements.backToArticlesBtn.setAttribute("version-id", versionId);
        elements.saveAddedSamplesBtn.getAttributeNames().filter(name => name.startsWith('data-tmp_')).forEach(attr => elements.saveAddedSamplesBtn.removeAttribute(attr));
        elements.saveAddedSamplesBtn.hidden = true;
        elements.articleDetailNote.hidden = true;

        try {
            const response = await fetch(`${API_BASE}/articles/${encodeURIComponent(versionId)}/${encodeURIComponent(articleId)}`);
            
            const data = await response.json();
            checkResponse(response, data);

            const articleTitle = data.article_title;
            elements.articleDetailTitle.textContent = articleTitle;
            elements.articleDetailId.textContent = articleId;
            Promise.all([
                displayArticleDetail("Samples", data).then(() => byId("articleSectionListSamples")?.insertAdjacentHTML('afterbegin', elements.addSampleContainer)),
                displayArticleDetail("Synonyms", data),
            ])
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        } finally {
            resetLoading(elements.updateArticlePageBtn);
        }
    }

    function updateArticlePageFunction() {
        setLoading(elements.updateArticlePageBtn);

        const versionId = elements.backToArticlesBtn.getAttribute("version-id");
        const articleId = byId("articleDetailId").textContent;

        showArticleDetail(versionId, articleId);
    }

    async function displayArticleDetail(keyWord, data) {
        const articleDetailX = elements["articleDetail" + keyWord];
        const keyWordShort = keyWord.toLowerCase().slice(0, -1);
        const [headerText, functionToDo, commonFunctionToDo] = keyWord == "Samples"
            ? [
                "Примеры",
                (id, cls) => elements.icons.texts.syn(`generateSynonym('${escapeHtml(id)}')`, cls, 'title="Сгенерировать синонимы"', "do"),
                () => elements.icons.texts.syn(`generateSynonymsAll(this)`, "section-header-control", 'title="Сгенерировать синонимы"')
            ]
            : [
                "Синонимы",
                (id, cls) => elements.icons.save(`saveSynonymAsSample('${escapeHtml(id)}')`, cls, 'title="Сохранить синоним как пример"'),
                () => elements.icons.save(`saveSynonymsAsSamples(this)`, "section-header-control", 'title="Сохранить все синонимы"')
            ];

        try {
            const dataEntries = Object.entries(data[keyWord.toLowerCase()]);
            let html = `
                <div class="article-intents-section-header accordion-header">
                    <h3>${headerText} (${dataEntries.length})</h3>
                    <div class="section-header-controls">
                        ${commonFunctionToDo()}
                        ${elements.icons.trashBin(`deleteIntents(this, '${headerText}')`, "section-header-control", `title="Удалить ${headerText.toLowerCase()}"`)}
                        ${elements.icons.arrow(`toggleAccordion(event, 'section-header-control', false)`, "section-header-control", 'title="Свернуть"')}
                    </div>
                </div>
                <div class="article-intents-section-list accordion-content" id="articleSectionList${keyWord}">
            `;

            if (dataEntries.length > 0)
                for (const [id, text] of dataEntries) {
                    html += `
                        <div class="intent-item">
                            <span class="intent-text" id="${id}">${escapeHtml(text)}</span>
                            <div class="intent-item-controls">
                                ${functionToDo(id, "intent-item-control")}
                                ${elements.icons.trashBin(
                                    `delete${keyWord.slice(0, -1)}(this, '${escapeHtml(id)}')`, 
                                    "intent-item-control", 
                                    `title="Удалить ${headerText.slice(0, -1).toLowerCase()}"`
                                )}
                            </div>
                        </div>
                    `;
                }
            else
                html += `
                    <div class="intent-item">
                        <span class="intent-text">${escapeHtml(`${headerText} отсутствуют`)}</span>
                    </div>
                `;

            articleDetailX.innerHTML = html + '</div>';
        } catch (error) {
            showToast(`Не удалось загрузить ${headerText.toLowerCase()}`, 'error');
            elements[articleDetailX].innerHTML = elements.error(error.message);
        }
    }

    // Save sample in article - caused by 'Enter'
    function newSampleEnterSave(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            saveAddedSample(event);
        }
    }

    // Save sample in article
    function saveAddedSample(event) {
        event.stopPropagation();

        const parent = event.currentTarget.closest(".intent-item");
        const text = parent.firstElementChild.value;
        if (!text) {
            showToast("Введите пример вопроса", 'error');
            return;
        }

        const id = `tmp_${performance.now().toString(32).replace('.', '_')}`;
        elements.saveAddedSamplesBtn.dataset[id] = text;
        elements.saveAddedSamplesBtn.hidden = false;
        elements.articleDetailNote.hidden = false;
        parent.remove();

        const html = `
            <div class="intent-item">
                <span class="intent-text" id="${id}">${escapeHtml(text)}</span>
                <div class="intent-item-controls">
                    ${elements.icons.trashBin(`deleteSample(this, '${id}')`, "intent-item-control", 'title="Удалить черновик примера"')}
                </div>
            </div>
        `;
        byId("articleSectionListSamples")?.insertAdjacentHTML('afterbegin', elements.addSampleContainer + html);
    }

    // Save addded samples to index
    async function saveAddedSamplesFunction() {
        setLoading(elements.updateArticlePageBtn);
        setLoading(elements.saveAddedSamplesBtn);

        try {
            const versionId = elements.backToArticlesBtn.getAttribute("version-id");
            if (!versionId) throw Error("Версия не найдена");

            const dataset = Object.entries(elements.saveAddedSamplesBtn.dataset).flatMap(([k, v]) => k.startsWith("tmp_") ? [v] : []);
            if (!dataset.length) {
                showToast(`Примеры вопросов не найдены`, 'info');
                return;
            }

            const articleId = elements.articleDetailId.textContent;
            const articleTitle = elements.articleDetailTitle.textContent;
            if (!articleId || !articleTitle) throw Error("Перезагрузите страницу");

            const versionsResponse = await fetch(`${API_BASE}/versions`);
            const versionsData = await versionsResponse.json();
            checkResponse(versionsResponse, versionsData);

            const version = versionsData.versions.find(el => el.version_id == versionId);
            if (!version) throw Error("Версия не найдена");
            
            const activate = version.is_active || false, pin = version.is_pin || false;
            const query = [{ "id": articleId, "title": articleTitle, "samples": dataset }];
            const url = `${API_BASE}/reindex?update_current=true&activate=${activate}&pin=${pin}&llm=false`;

            const reindexResponse = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ data: query })
            });

            const reindexData = await reindexResponse.json();
            checkResponse(reindexResponse, reindexData);

            elements.saveAddedSamplesBtn.hidden = true;
            elements.articleDetailNote.hidden = true;

            showToast(`Задача создана: ${reindexData.task_id}`, 'info');
        } catch {
            showToast(`Ошибка: ${error.message}`, 'error');
        } finally {
            resetLoading(elements.updateArticlePageBtn);
            resetLoading(elements.saveAddedSamplesBtn);
        }
    }

    // Generate synonyms for samples - general function
    async function generateSynonyms(sampleIds) {
        try {
            const versionId = elements.backToArticlesBtn.getAttribute("version-id");
            const articleId = elements.articleDetailId.textContent;

            const response = await fetch(`${API_BASE}/llm/${versionId}/${articleId}`, { 
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ ids: sampleIds })
            });

            const data = await response.json();
            checkResponse(response, data);

            return data
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        }
    }

    // Generate synonyms for sample
    async function generateSynonym(sampleId) {
        if (!await showConfirm('Сгенерировать синонимы для этого примера?')) return;

        const data = await generateSynonyms([sampleId])
        showToast(`Задача создана: ${data.task_id}`, 'info');
        setTimeout(() => showToast(`Чтобы увидеть изменения, нажмите кнопку "Обновить"`, 'info'), 1000);
    }

    // Get samples for generating synonyms
    async function generateSynonymsAll(element) {
        if (!await showConfirm('Сгенерировать синонимы для всех примеров?')) return;
    
        const samplesListElement = element.closest(".article-intents-section-header").nextElementSibling;
        const sampleIds = Array.from(samplesListElement.children).map(el => el.firstElementChild.id);
        const data = await generateSynonyms(sampleIds);
        showToast(`Задача создана: ${data.task_id}`, 'info');
        setTimeout(() => showToast(`Чтобы увидеть изменения, нажмите кнопку "Обновить"`, 'info'), 1000);
    }

    // Delete samples or synonyms - general function
    async function deleteIntentsGeneral(intentIds) {
        const versionId = elements.backToArticlesBtn.getAttribute("version-id");
        const articleId = elements.articleDetailId.textContent;

        const response = await fetch(
            `${API_BASE}/articles/${encodeURIComponent(versionId)}/${encodeURIComponent(articleId)}/ids`,
            {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ ids: intentIds })
            }
        );

        const data = await response.json();
        checkResponse(response, data);

        return data;
    }

    // Delete sample
    async function deleteSample(element, sampleId) {
        if (sampleId && sampleId?.startsWith("tmp")) {
            if (!await showConfirm('Удалить черновик примера?')) return;

            delete elements.saveAddedSamplesBtn.dataset[sampleId];
            element.closest(".intent-item").remove();
            showToast(`Черновик примера вопроса удален`, 'success');
            return;
        }

        if (!await showConfirm('Удалить этот пример?')) return;
        try {
            const data = await deleteIntentsGeneral([sampleId]);

            showToast(`Задача создана: ${data.task_id}`, 'info');
            setTimeout(() => showToast(`Чтобы увидеть изменения, нажмите кнопку "Обновить"`, 'info'), 1000);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        }
    }

    // Delete synonym
    async function deleteSynonym(element, synonymId) {
        if (!await showConfirm('Удалить этот синоним?')) return;

        try {
            const data = await deleteIntentsGeneral([synonymId]);

            showToast(`Задача создана: ${data.task_id}`, 'info');
            setTimeout(() => showToast(`Чтобы увидеть изменения, нажмите кнопку "Обновить"`, 'info'), 1000);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        }
    }

    // Delete samples or synonyms
    async function deleteIntents(element, headerText) {
        if (!await showConfirm(`Удалить все ${headerText.toLowerCase()}?`)) return;

        try {
            const headerH3 = element.closest(".section-header-controls").previousElementSibling;
            const list = headerH3.parentElement.nextElementSibling;
            const textElements = Array.from(list.children);
            const ids = textElements.map(el => el.firstElementChild.id);
            
            const data = await deleteIntentsGeneral(ids);

            showToast(`Задача создана: ${data.task_id}`, 'info');
            setTimeout(() => showToast(`Чтобы увидеть изменения, нажмите кнопку "Обновить"`, 'info'), 1000);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        }
    }

    // Save synonyms as samples (and delete synonyms) - general function
    async function saveSynonymAsSampleGeneral(synonymIds) {
        try {
            const versionId = elements.backToArticlesBtn.getAttribute("version-id");
            const articleId = elements.articleDetailId.textContent;

            const response = await fetch(
                `${API_BASE}/articles/${encodeURIComponent(versionId)}/${encodeURIComponent(articleId)}/convert`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ ids: synonymIds })
                }
            );

            const data = await response.json();
            checkResponse(response, data);

            return data
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        }
    }

    // Save synonym as sample
    async function saveSynonymAsSample(synonymId) {
        if (!await showConfirm(`Сохранить синоним как пример вопроса?`)) return;
        const data = await saveSynonymAsSampleGeneral([synonymId]);
        showToast(`Задача создана: ${data.task_id}`, 'info');
        setTimeout(() => showToast(`Чтобы увидеть изменения, нажмите кнопку "Обновить"`, 'info'), 1000);
    }

    // Save synonyms as samples
    async function saveSynonymsAsSamples(element) {
        if (!await showConfirm(`Сохранить все синонимы как примеры вопросов?`)) return;

        const list = element.closest(".article-intents-section-header").nextElementSibling;
        const synonymIds = Array.from(list.children).map(el => el.querySelector(".intent-text").id);
        const data = await saveSynonymAsSampleGeneral(synonymIds);

        showToast(`Задача создана: ${data.task_id}`, 'info');
        setTimeout(() => showToast(`Чтобы увидеть изменения, нажмите кнопку "Обновить"`, 'info'), 1000);
    }

    // Database
    async function loadDatabase() {
        setSpinner(elements.databaseContainer, "Загрузка");

        try {
            const response = await fetch(`${API_BASE}/database`);

            const data = await response.json();
            checkResponse(response, data);

            displayDatabase(data);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        } finally {
            resetSpinner(elements.databaseContainer, "Обновить");
        }
    }

    // Display database
    function displayDatabase(data) {
        console.log("Функционал не реализован")
    }

    // Stop-words
    async function loadStopWords() {
        setLoading(elements.getStopWordsBtn);

        try {
            const response = await fetch(`${API_BASE}/stopwords`);
            
            const data = await response.json();
            checkResponse(response, data);

            displayStopWords(data);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        } finally {
            resetLoading(elements.getStopWordsBtn);
        }
    }

    // Display stop-words
    function displayStopWords(data) {
        elements.stopWordsNoteTotal.textContent = data.count;

        let html = '';
        data.stop_words.forEach(stopWord => html += `
            <div class="stop-word">
                <p class="clickable-text" onclick="copyToClipboard(this, event)">${escapeHtml(stopWord)}</p>
                ${elements.icons.trashBin('deleteStopWord(this)', "stop-word-btn")}
            </div>
        `);

        elements.stopWordsList.innerHTML = html + elements.addStopWordContainer;
    }

    // Delete stop-word
    function deleteStopWord(element) {
        element.closest(".stop-word").remove();
        showToast("Стоп-слово удалено")
    }

    // Save stop-word - caused by 'Enter'
    function newStopWordEnterSave(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            saveStopWord(event);
        }
    }

    // Save stop-word
    function saveStopWord(event) {
        event.stopPropagation();

        const element = event.currentTarget;
        const stopWordElement = element.closest(".stop-word");
        const inputElement = stopWordElement.firstElementChild;
        const text = inputElement.value;
        const btnElement = stopWordElement.lastElementChild;
        const stopWordsList = elements.stopWordsList;

        if (!text) {
            showToast("Введите стоп-слово", 'error');
            return;
        }

        stopWordElement.classList.remove("add");
        inputElement.outerHTML = `<p class="clickable-text" onclick="copyToClipboard(this, event)">${escapeHtml(text)}</p>`;
        btnElement.outerHTML = elements.icons.trashBin('deleteStopWord(this)', "stop-word-btn", 'title="Убрать"');
        stopWordsList.innerHTML += elements.addStopWordContainer;

        byId("stopWordsNoteTotal").innerHTML = `Всего стоп-слов: ${stopWordsList.querySelectorAll(".stop-word:not(.add)").length}`;
        stopWordsList.querySelector('.stop-word input[type="search"]').focus();

        showToast("Стоп-слово добавлено");
    }

    // Save all stop-words
    async function saveStopWords() {
        const stopWords = [...elements.stopWordsList.querySelectorAll(".stop-word .clickable-text")].map(el => el.textContent.trim()).filter(Boolean);
        if (!stopWords.length) {
            showToast(`Нет данных для сохранения`, 'error');
            return;
        }

        try {
            const response = await fetch(`${API_BASE}/stopwords`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ stop_words: stopWords })
            });

            const data = await response.json();
            checkResponse(response, data);

            const { total_count, added, deleted } = data;
            showToast(`Всего стоп слов: ${total_count}. Добавлено: ${added.length}. Удалено: ${deleted.length}`, 'success');
            loadStopWords();
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        }
    }

    // LLM Config - Load
    async function loadLlmConfig() {
        setLoading(elements.loadLlmConfigBtn);

        try {
            const response = await fetch(`${API_BASE}/llm/config`);

            const data = await response.json();
            checkResponse(response, data);

            displayLlmConfig(data);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        } finally {
            initLlmSections();
            resetLoading(elements.loadLlmConfigBtn);
        }
    }

    // LLM Config - Display
    function displayLlmConfig(data, section) {
        const configSections = {
            connection: () => {
                elements.llmUrl.value = data.llm_url || '';
                elements.llmModel.value = data.llm_model || '';
            },
            parameters: () => {
                elements.llmTemperature.value = data.llm_temperature ?? 0.4;
                elements.llmTopP.value = data.llm_top_p ?? 0.7;
                elements.llmFrequencyPenalty.value = data.llm_frequency_penalty ?? 0.2;
                elements.llmRepeatPenalty.value = data.llm_repeat_penalty ?? 1.1;
                elements.llmPresencePenalty.value = data.llm_presence_penalty ?? 0.1;
            },
            prompt: () => {
                elements.llmPrompt.value = data.llm_prompt || '';
            },
        };
        if (section in configSections) {
            configSections[section]();
            return;
        }
        if (!section) Object.values(configSections).map(f => f());
    }

    // LLM Section - Initialize headers and hints
    function initLlmSections() {
        const sections = byId("page-llm").querySelectorAll(".llm-config-section[section]");
        sections.forEach(section => {
            section.querySelector(".section-header-controls").innerHTML = (
                elements.icons.reset(`resetLlmParams(event)`, '', 'title="Сбросить изменения"') +
                elements.icons.arrow(`toggleAccordion(event, 'section-header-control', false)`, "section-header-control", 'title="Свернуть"')
            );
        });
        
        const hintMapping = {
            "llmTemperature": "0.0-2.0 Креативность ответов",
            "llmTopP": "0.0-1.0 Ядро выборки",
            "llmFrequencyPenalty": "-2.0-2.0 Штраф за частоту слов",
            "llmRepeatPenalty": "0.0-2.0 Штраф за повторы",
            "llmPresencePenalty": "-2.0-2.0 Штраф за повторение тем",
            "llmUrl": "URL API-эндпоинта LLM",
            "llmModel": "Название модели для генерации",
        };
        Object.keys(hintMapping).forEach(id => {
            const label = elements[id].previousElementSibling;
            label.innerHTML = 
                `<span class="llm-controls-param-hint">${elements.icons.question('', '', `title="${hintMapping[id]}"`)}</span> ` +
                label.textContent;
        });
    }

    // LLM Config - Save
    async function saveLlmConfig() {
        setLoading(elements.saveLlmConfigBtn);

        const payload = {
            llm_url: elements.llmUrl.value,
            llm_model: elements.llmModel.value,
            llm_temperature: parseFloat(elements.llmTemperature.value),
            llm_top_p: parseFloat(elements.llmTopP.value),
            llm_frequency_penalty: parseFloat(elements.llmFrequencyPenalty.value),
            llm_repeat_penalty: parseFloat(elements.llmRepeatPenalty.value),
            llm_presence_penalty: parseFloat(elements.llmPresencePenalty.value),
            llm_prompt: elements.llmPrompt.value,
        };

        const isIdentical = await checkLlmConfigDiffer(payload);
        if (isIdentical) {
            showToast('Настройки LLM сохранены', 'success');
            resetLoading(elements.saveLlmConfigBtn);
            return;
        }

        try {
            const response = await fetch(`${API_BASE}/llm/config`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();
            checkResponse(response, data);

            showToast('Настройки LLM сохранены', 'success');
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        } finally {
            resetLoading(elements.saveLlmConfigBtn);
        }
    }

    //
    async function checkLlmConfigDiffer(payload) {
        const newData = JSON.stringify(payload);

        const response = await fetch(`${API_BASE}/llm/config`);
        const data = await response.json();
        const oldData = JSON.stringify(data);

        return newData === oldData;
    }

    // LLM Config - Reset parameters to default
    async function resetLlmParams(event) {
        if (!await showConfirm(`Вы уверены, что хотите сбросить изменения?`))
            return;

        event.stopPropagation();
        const element = event.currentTarget;
        
        try {
            const response = await fetch(`${API_BASE}/llm/config`);
            
            const data = await response.json();
            checkResponse(response, data);

            const section = element.closest(".llm-config-section").getAttribute("section");
            displayLlmConfig(data, section);
        } catch (error) {
            showToast(`Ошибка: ${error.message}`, 'error');
        }
    }

    // Copy data to clipboard
    async function copyToClipboard(element, event) {
        event.stopPropagation();

        const text = element.textContent;
        navigator.clipboard.writeText(text).then(() => {
            element.classList.add("copied");
            showToast("Скопировано в буфер обмена", "success")
            setTimeout(() => element.classList.remove("copied"), 500);
        }).catch(e => { });
    }

    // Download .json template
    function downloadJsonTemplate(event) {
        event.stopPropagation();
        const jsonContent = indexJsonPlaceholder;
        downloadFile(jsonContent, 'template.json', 'application/json');
    }

    // Download .xlsx template (using SheetJS for true Excel format)
    function downloadXlsxTemplate(event) {
        event.stopPropagation();

        // Create worksheet data (array of arrays)
        const data = [
            ['id', 'title', 'samples'],
            ['article_001', 'Заголовок', 'пример вопроса 1'],
            ['article_001', 'Заголовок', 'пример вопроса 2'],
            ['article_002', 'Заголовок 2', 'пример вопроса'],
        ];

        // Create worksheet and workbook
        const ws = XLSX.utils.aoa_to_sheet(data);

        // Set column widths
        ws['!cols'] = [
            { wch: 30 },
            { wch: 50 },
            { wch: 100 },
        ];

        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, 'Template');

        // Generate and download file
        XLSX.writeFile(wb, 'template.xlsx');
    }

    // Download .txt template
    function downloadTxtTemplate(event) {
        event.stopPropagation();
        copyToClipboard(event.currentTarget.firstElementChild, event);
    }

    // Trigger file download
    function downloadFile(content, filename, mimeType) {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // Utility functions
    function expandSidebar(event) {
        event.stopPropagation();
        const element = event.currentTarget;
        element.setAttribute("onclick", "collapseSidebar(event)");
        elements.sidebar.classList.add("open");
    }

    function collapseSidebar(event) {
        event.stopPropagation();
        const element = event.currentTarget;
        element.setAttribute("onclick", "expandSidebar(event)");
        elements.sidebar.classList.remove("open");
    }

    function setLoading(button, msg) {
        if (button.querySelector(".spinner")) return;
        button.dataset.originalText = button.textContent;
        setSpinner(button, msg || "Загрузка");
    }

    function resetLoading(button) {
        resetSpinner(button, button.dataset.originalText || button.innerHTML);
    }

    async function setSpinner(element, msg) {
        element.disabled = true;
        element.innerHTML = elements.spinner(msg);
        element.setAttribute("timestamp", Date.now());
    }

    async function resetSpinner(element, innerHTML) {
        const elementTimestamp = element.getAttribute("timestamp");
        if (!elementTimestamp) return;

        const remainingTime = +elementTimestamp + 500 - Date.now();
        if (remainingTime > 0) {
            await new Promise(res => setTimeout(res, remainingTime));
        }

        element.innerHTML = innerHTML;
        element.removeAttribute("timestamp");
        element.disabled = false;
    }

    // Toggle accordion (collapse or expand section)
    function toggleAccordion(event, cls, toOpen) {
        event.stopPropagation();
        const element = event.currentTarget;
        const commonParent = element.closest(".accordion");
        if (!commonParent) return;

        const header = commonParent.querySelector(".accordion-header");
        const content = commonParent.querySelector(".accordion-content");
        if (!header || !content) return;

        if (toOpen) {
            commonParent.classList.remove("collapsed");
            element.outerHTML = elements.icons.arrow(`toggleAccordion(event, '${cls}', false)`, cls, 'title="Свернуть"');
        } else {
            commonParent.classList.add("collapsed");
            element.outerHTML = elements.icons.arrow(`toggleAccordion(event, '${cls}', true)`, cls, 'title="Развернуть"', "down");
        }
    }

    function checkInputTypeSearch(element) {
        if (element.value) {
            element.classList.remove("error");
        } else {
            element.classList.add("error");
        }
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function fromIsoTimeFormat(dateIso) {
        const date = new Date(dateIso);
        if (!dateIso || Number.isNaN(date.getDay()))
            return dateIso;
        return date.toLocaleString('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        }).replace(',', '');
    }

    // Toast container (created once)
    let toastContainer = null;
    function getToastContainer() {
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container';
            toastContainer.id = 'toastContainer';
            document.body.appendChild(toastContainer);
        }
        return toastContainer;
    }

    function showToast(message, status) {
        const effectiveStatus = status || 'info';

        const colorMap = {
            success: 'var(--success-color)',
            error: 'var(--error-color)',
            info: 'var(--secondary-color)'
        };

        const backgroundColor = colorMap[effectiveStatus] || colorMap.info;

        const container = getToastContainer();

        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${effectiveStatus}`;
        toast.style.backgroundColor = backgroundColor;
        toast.style.color = '#ffffff';
        toast.style.display = 'flex';
        toast.style.alignItems = 'center';
        toast.style.gap = 'var(--spacing-s)';

        // Check if message is a task creation message
        const taskMatch = message.match(/^Задача создана:\s*(.+)$/);
        if (taskMatch) {
            const taskId = taskMatch[1].trim();

            // Text part
            const textSpan = document.createElement('span');
            textSpan.className = 'toast-text';
            textSpan.textContent = message;
            toast.appendChild(textSpan);

            // Pin icon
            const pinContainer = document.createElement('div');
            pinContainer.style.cssText = 'cursor: pointer; flex-shrink: 0; display: inline-flex; align-items: center;';
            pinContainer.innerHTML = elements.icons.pin('', '', '', 'pin');
            pinContainer.querySelector('.icon-wrapper').addEventListener('click', (e) => {
                e.stopPropagation();
                pinToast(taskId, toast);
            });
            toast.appendChild(pinContainer);
        } else {
            toast.textContent = message;
        }

        container.appendChild(toast);

        // Remove after 3 seconds with fade out
        setTimeout(() => {
            toast.classList.add('toast-hiding');
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
                // Clean up container if empty
                if (container.children.length === 0) {
                    container.remove();
                    toastContainer = null;
                }
            }, 200);
        }, 3000);
    }

    // Pin a toast (create pinned task card)
    function pinToast(taskId, toastElement) {
        Swal.fire({
            title: 'Закрепить задачу?',
            text: `Закрепить отслеживание задачи ${taskId}?`,
            showCancelButton: true,
            color: 'var(--text-color)',
            confirmButtonColor: 'var(--primary-color)',
            cancelButtonColor: 'var(--secondary-color)',
            confirmButtonText: 'Закрепить',
            cancelButtonText: 'Отмена',
        }).then((result) => {
            if (result.isConfirmed) {
                // If there's already a pinned task, unpin it
                if (pinnedTaskId && pinnedTaskId !== taskId) {
                    unpinCurrentTask();
                }

                pinnedTaskId = taskId;

                // Remove auto-hide from toast
                toastElement.classList.add('toast-pinned');

                // Create the pinned task card
                createPinnedTaskCard(taskId);
            }
        });
    }

    // Unpin current task
    function unpinCurrentTask() {
        if (pinnedTaskInterval) {
            clearInterval(pinnedTaskInterval);
            pinnedTaskInterval = null;
        }
        if (pinnedTaskCard) {
            pinnedTaskCard.remove();
            pinnedTaskCard = null;
        }
        pinnedTaskId = null;
    }

    // Create pinned task card in top-right corner
    function createPinnedTaskCard(taskId) {
        // Remove existing card if any
        if (pinnedTaskCard) {
            pinnedTaskCard.remove();
        }

        const stepMapping = {
            "starting": "Старт процесса",
            "saving_db": "Сохранение в БД",
            "generating_embeddings": "Генерация эмбеддингов",
            "generating_synonyms": "Генерация синонимов",
            "completed": "Завершен",
        };

        // Create card element
        const card = document.createElement('div');
        card.className = 'pinned-task-card';
        card.id = 'pinnedTaskCard';
        card.innerHTML = `
            <div class="pinned-task-header">
                <span class="pinned-task-title">Задача: <strong class="pinned-task-id">${escapeHtml(taskId)}</strong></span>
                <span class="pinned-task-unpin" title="Открепить">${elements.pin('', '', '', 'unpin')}</span>
            </div>
            <div class="pinned-task-step">
                <strong>Шаг:</strong> <span class="pinned-task-step-text">Загрузка...</span>
            </div>
            <div class="pinned-task-progress">
                <div class="pinned-task-progress-bar" style="--progress: 0%;" data-text="0%">0%</div>
            </div>
        `;

        document.body.appendChild(card);
        pinnedTaskCard = card;

        // Unpin handler
        card.querySelector('.pinned-task-unpin').addEventListener('click', (e) => {
            e.stopPropagation();
            unpinCurrentTask();
            // Also remove the pinned class from toast
            document.querySelectorAll('.toast-pinned').forEach(t => t.classList.remove('toast-pinned'));
        });

        // Click handler for the card
        card.addEventListener('click', () => {
            if (pinnedTaskCompleted) {
                // Task is done - open versions page, remove card
                showPage('versions');
                unpinCurrentTask();
                document.querySelectorAll('.toast-pinned').forEach(t => t.classList.remove('toast-pinned'));
            } else {
                // Task is still running - open task detail page
                showPage('task-detail');
                byId('taskDetailId').textContent = taskId;
                fetchTaskDetailForCard(taskId);
            }
        });

        // Start polling
        pinnedTaskCompleted = false;
        fetchTaskDetailForCard(taskId);
        pinnedTaskInterval = setInterval(() => {
            if (!pinnedTaskCompleted) {
                fetchTaskDetailForCard(taskId);
            }
        }, 3000);
    }

    let pinnedTaskCompleted = false;

    // Fetch task detail for pinned card
    async function fetchTaskDetailForCard(taskId) {
        try {
            const response = await fetch(`${API_BASE}/task/${taskId}`);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || response.statusText);
            }

            const stepMapping = {
                "starting": "Старт процесса",
                "saving_db": "Сохранение в БД",
                "generating_embeddings": "Генерация эмбеддингов",
                "generating_synonyms": "Генерация синонимов",
                "completed": "Завершен",
            };

            const step = stepMapping[data.progress?.step] || 'Неизвестно';
            const current = data.progress?.current || 0;
            const total = data.progress?.total || 0;
            const percent = total > 0 ? (current * 100 / total).toFixed(2) : 0;

            // Update card
            if (pinnedTaskCard) {
                pinnedTaskCard.querySelector('.pinned-task-step-text').textContent = step;
                const progressBar = pinnedTaskCard.querySelector('.pinned-task-progress-bar');
                progressBar.style.setProperty('--progress', percent + '%');
                progressBar.setAttribute('data-text', percent + '%');
                progressBar.textContent = percent + '%';

                // Update progress bar color based on status
                progressBar.className = 'pinned-task-progress-bar';
                if (data.error) {
                    progressBar.classList.add('failed');
                    pinnedTaskCompleted = true;
                } else if (data.progress?.step === 'completed') {
                    progressBar.classList.add('done');
                    pinnedTaskCompleted = true;
                } else if (data.progress?.step) {
                    progressBar.classList.add('processing');
                }
            }

            if (pinnedTaskCompleted) {
                if (pinnedTaskInterval) {
                    clearInterval(pinnedTaskInterval);
                    pinnedTaskInterval = null;
                }
            }
        } catch (error) {
            console.error('Error fetching task detail:', error);
        }
    }

    // Show confirmation dialog using SweetAlert
    async function showConfirm(message) {
        const result = await Swal.fire({
            text: message,
            showCancelButton: true,
            color: 'var(--text-color)',
            confirmButtonColor: 'var(--primary-color)',
            cancelButtonColor: 'var(--secondary-color)',
            confirmButtonText: 'Подтвердить',
            cancelButtonText: 'Отмена',
        });
        return result.isConfirmed;
    }

    function tooltipMouseLeave(event) {
        event.currentTarget.classList.remove('visible');
    }

    function tooltipMouseEnter(event) {
        event.currentTarget.classList.add('visible');
    }

    function byId(id, space = document) {
        return space.getElementById(id);
    }

    function checkResponse(response, data) {
        if (!response.ok) throw new Error(data.detail || response.statusText);
    }

    // Make functions globally available for onclick handlers
    window.showPage = showPage;
    window.expandSidebar = expandSidebar;
    window.collapseSidebar = collapseSidebar;
    window.showTaskDetail = showTaskDetail;
    window.showVersionDetail = showVersionDetail;
    window.showVersionDetailPage = showVersionDetailPage;
    window.removeFilesItem = removeFilesItem;
    window.renameVersionEvent = renameVersionEvent;
    window.saveVersionName = saveVersionName;
    window.resetVersionName = resetVersionName;
    window.activateVersion = activateVersion;
    window.renameVersion = renameVersion;
    window.pinVersion = pinVersion;
    window.unpinVersion = unpinVersion;
    window.deleteVersion = deleteVersion;
    window.showArticleDetail = showArticleDetail;
    window.loadVersions = loadVersions;
    window.newSampleEnterSave = newSampleEnterSave;
    window.saveAddedSample = saveAddedSample;
    window.generateSynonymsAll = generateSynonymsAll;
    window.generateSynonym = generateSynonym;
    window.deleteSample = deleteSample;
    window.deleteSynonym = deleteSynonym;
    window.deleteIntents = deleteIntents;
    window.saveSynonymAsSample = saveSynonymAsSample;
    window.saveSynonymsAsSamples = saveSynonymsAsSamples;
    window.deleteSynonymsForArticle = deleteSynonymsForArticle;
    window.deleteIntentsForArticle = deleteIntentsForArticle;
    window.deleteArticle = deleteArticle;
    window.deleteQueueTask = deleteQueueTask;
    window.deleteStopWord = deleteStopWord;
    window.newStopWordEnterSave = newStopWordEnterSave;
    window.saveStopWord = saveStopWord;
    window.copyToClipboard = copyToClipboard;
    window.downloadJsonTemplate = downloadJsonTemplate;
    window.downloadXlsxTemplate = downloadXlsxTemplate;
    window.downloadTxtTemplate = downloadTxtTemplate;
    window.fromIsoTimeFormat = fromIsoTimeFormat;
    window.tooltipMouseEnter = tooltipMouseEnter;
    window.tooltipMouseLeave = tooltipMouseLeave;
    window.loadLlmConfig = loadLlmConfig;
    window.saveLlmConfig = saveLlmConfig;
    window.resetLlmParams = resetLlmParams;
    window.setSpinner = setSpinner;
    window.resetSpinner = resetSpinner;
    window.toggleAccordion = toggleAccordion;
    window.checkInputTypeSearch = checkInputTypeSearch;
    window.showToast = showToast;
    window.byId = byId;
    window.checkResponse = checkResponse;

    window.elements = elements;
    window.activeVersionId = activeVersionId;
    window.currentVersionId = currentVersionId;

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
