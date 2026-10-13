const { createApp, ref, computed, onMounted, nextTick } = Vue;

createApp({
  setup() {
    // 导航选项卡: 'dashboard' | 'preview' | 'extract' | 'storage'
    const activeTab = ref('dashboard');

    // 系统状态与全局配置
    const sysStatus = ref({
      mongodb_connected: false,
      storage_mode: 'local_fallback',
      mongodb_uri: '',
      newapi_url: '',
      newapi_model: ''
    });
    const showConfigModal = ref(false);
    const systemConfigForm = ref({
      mongodb_uri: '',
      newapi_url: '',
      newapi_key: '',
      newapi_model: ''
    });

    // --- 页面 1: 工作台 / 爬虫 ---
    const crawlForm = ref({
      task_id: '',
      urlsText: '',
      delay: 1.0
    });
    const isCrawling = ref(false);
    const logs = ref([]);
    const logBox = ref(null);
    const taskList = ref([]);

    const generateNewTaskId = () => {
      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const timeStr = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
      const randStr = Math.random().toString(36).substring(2, 6);
      crawlForm.value.task_id = `task_${timeStr}_${randStr}`;
    };

    const fillSampleUrl = (type) => {
      if (type === 'baike') {
        crawlForm.value.urlsText = 'https://baike.baidu.com/item/%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD/9180';
      } else if (type === 'news') {
        crawlForm.value.urlsText = 'https://news.sina.com.cn';
      }
    };

    const appendLog = (msg, level = 'INFO') => {
      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const time = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
      logs.value.push({ time, level, message: msg });
      nextTick(() => {
        if (logBox.value) {
          logBox.value.scrollTop = logBox.value.scrollHeight;
        }
      });
    };

    const clearLogs = () => {
      logs.value = [];
    };

    const startCrawlTask = async () => {
      const rawUrls = crawlForm.value.urlsText.split('\n').map(u => u.trim()).filter(Boolean);
      if (rawUrls.length === 0) {
        alert('请输入至少一个有效的待爬取网址！');
        return;
      }

      isCrawling.value = true;
      appendLog(`开始执行抓取任务: ${crawlForm.value.task_id}，共 ${rawUrls.length} 个网址...`, 'INFO');

      try {
        const resp = await fetch('/api/crawl', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            task_id: crawlForm.value.task_id,
            urls: rawUrls,
            delay: crawlForm.value.delay
          })
        });

        const data = await resp.json();
        if (!resp.ok) {
          throw new Error(data.detail || '爬取失败');
        }

        appendLog(`任务全部完成！成功抓取并生成 ${data.results_count} 个 Markdown 文档`, 'SUCCESS');
        await fetchTaskList();
        // 自动选中当前任务并提示
        selectedTaskId.value = crawlForm.value.task_id;
      } catch (err) {
        appendLog(`发生错误: ${err.message}`, 'ERROR');
        alert(`爬取失败: ${err.message}`);
      } finally {
        isCrawling.value = false;
      }
    };

    const stopCrawlTask = async () => {
      if (!crawlForm.value.task_id) return;
      try {
        await fetch(`/api/tasks/${crawlForm.value.task_id}/stop`, { method: 'POST' });
        appendLog('已发送停止指令...', 'WARN');
      } catch (e) {
        console.error(e);
      }
    };

    const fetchTaskList = async () => {
      try {
        const resp = await fetch('/api/tasks');
        if (resp.ok) {
          taskList.value = await resp.json();
          if (taskList.value.length > 0 && !selectedTaskId.value) {
            selectedTaskId.value = taskList.value[0].task_id;
          }
        }
      } catch (e) {
        console.error(e);
      }
    };

    // --- 页面 2: MD 预览 ---
    const selectedTaskId = ref('');
    const currentTaskDetail = ref({});

    const loadTaskDetail = async () => {
      if (!selectedTaskId.value) return;
      try {
        const resp = await fetch(`/api/tasks/${selectedTaskId.value}`);
        if (resp.ok) {
          currentTaskDetail.value = await resp.json();
        }
      } catch (e) {
        console.error(e);
      }
    };

    const renderedMarkdownHtml = computed(() => {
      const content = currentTaskDetail.value.md_content || '';
      if (!content) return '<p class="text-slate-500">暂无内容，请先执行爬虫任务并生成 Markdown</p>';
      if (window.marked && typeof window.marked.parse === 'function') {
        return marked.parse(content);
      }
      // 离线/CDN失败简易 Markdown 渲染兜底
      return content
        .replace(/^### (.*$)/gim, '<h3 class="text-base font-bold my-2 text-slate-200">$1</h3>')
        .replace(/^## (.*$)/gim, '<h2 class="text-lg font-bold my-2 text-slate-100">$1</h2>')
        .replace(/^# (.*$)/gim, '<h1 class="text-xl font-extrabold my-3 pb-1 border-b border-slate-700 text-white">$1</h1>')
        .replace(/^\> (.*$)/gim, '<blockquote class="border-l-4 border-indigo-500 pl-3 py-1 my-2 bg-slate-800/60 text-slate-300">$1</blockquote>')
        .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/gim, '<em>$1</em>')
        .replace(/\n/gim, '<br>');
    });

    const viewTaskPreview = async (taskId) => {
      selectedTaskId.value = taskId;
      await loadTaskDetail();
      activeTab.value = 'preview';
    };

    const goToExtraction = async (taskId) => {
      selectedTaskId.value = taskId;
      await loadTaskDetail();
      activeTab.value = 'extract';
    };

    const downloadCurrentMd = () => {
      if (!selectedTaskId.value) return;
      window.open(`/api/tasks/${selectedTaskId.value}/download-md`, '_blank');
    };

    const copyMdText = () => {
      if (currentTaskDetail.value.md_content) {
        navigator.clipboard.writeText(currentTaskDetail.value.md_content);
        alert('Markdown 原文已成功复制到剪贴板！');
      }
    };

    // --- 页面 3: 字段配置与智能提取 ---
    const fieldConfig = ref([
      {
        name: '基础概览',
        desc: '条目的基本名称、身份地位与成立/生卒时间',
        sub_fields: [
          { name: '名称', desc: '页面词条全称' },
          { name: '领域/身份', desc: '所属行业、职业或专业技术领域' },
          { name: '重要时间', desc: '出生年份、创建日期或代表年份' }
        ]
      },
      {
        name: '核心成就与特色',
        desc: '页面中记载的关键成果、荣誉或主打特性',
        sub_fields: [
          { name: '主要成果', desc: '获得的最高成就或最具影响力的代表作' },
          { name: '核心特色', desc: '区别于其他事物的关键亮点' }
        ]
      }
    ]);

    const isAiAccordionOpen = ref(false);
    const aiForm = ref({
      api_url: 'https://api.openai.com/v1/chat/completions',
      model: 'gpt-4o-mini',
      timeout: 60,
      max_retries: 3
    });

    const isExtracting = ref(false);
    const extractionResult = ref(null);
    const extractionSaveSummary = ref(null);

    const toggleAiParamAccordion = () => {
      isAiAccordionOpen.value = !isAiAccordionOpen.value;
    };

    const addMainField = () => {
      fieldConfig.value.push({
        name: '',
        desc: '',
        sub_fields: []
      });
    };

    const removeMainField = (idx) => {
      fieldConfig.value.splice(idx, 1);
    };

    const addSubField = (mainIdx) => {
      fieldConfig.value[mainIdx].sub_fields.push({
        name: '',
        desc: ''
      });
    };

    const removeSubField = (mainIdx, subIdx) => {
      fieldConfig.value[mainIdx].sub_fields.splice(subIdx, 1);
    };

    const clearFields = () => {
      fieldConfig.value = [];
    };

    const applyTemplate = async (templateId) => {
      try {
        const resp = await fetch('/api/templates');
        const list = await resp.json();
        const t = list.find(item => item.id === templateId);
        if (t) {
          fieldConfig.value = JSON.parse(JSON.stringify(t.fields));
          alert(`已成功加载「${t.name}」！`);
        }
      } catch (e) {
        console.error(e);
      }
    };

    const startAIExtraction = async () => {
      if (!selectedTaskId.value) {
        alert('请先选择一个已爬取的任务！');
        return;
      }
      if (fieldConfig.value.length === 0) {
        alert('请至少配置一个主字段！');
        return;
      }

      isExtracting.value = true;
      extractionResult.value = null;
      extractionSaveSummary.value = null;

      try {
        const resp = await fetch('/api/extract', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            task_id: selectedTaskId.value,
            fields: fieldConfig.value,
            ai_config: aiForm.value
          })
        });

        const data = await resp.json();
        if (!resp.ok) {
          throw new Error(data.detail || '提取失败');
        }

        extractionResult.value = data.results;
        extractionSaveSummary.value = data.storage_summary;
        await fetchStorageData();
      } catch (err) {
        alert(`字段提取失败: ${err.message}`);
      } finally {
        isExtracting.value = false;
      }
    };

    const copyExtractionJson = () => {
      if (extractionResult.value) {
        navigator.clipboard.writeText(JSON.stringify(extractionResult.value, null, 2));
        alert('提取结果 JSON 已复制！');
      }
    };

    // --- 页面 4: MongoDB 数据存储查看 ---
    const currentStorageTable = ref('tasks');
    const storageSearchTaskId = ref('');
    const storageRows = ref([]);

    const currentStorageTableTitle = computed(() => {
      if (currentStorageTable.value === 'tasks') return '基础任务表 (crawl_tasks)';
      if (currentStorageTable.value === 'main_fields') return '主字段表 (main_fields)';
      if (currentStorageTable.value === 'sub_fields') return '子字段表 (sub_fields)';
      return '';
    });

    const switchStorageTable = (tbl) => {
      currentStorageTable.value = tbl;
      fetchStorageData();
    };

    const fetchStorageData = async () => {
      try {
        const url = `/api/storage/data?table=${currentStorageTable.value}&task_id=${encodeURIComponent(storageSearchTaskId.value || '')}`;
        const resp = await fetch(url);
        if (resp.ok) {
          storageRows.value = await resp.json();
        }
      } catch (e) {
        console.error(e);
      }
    };

    const filterSubFieldsByMain = (mainFieldId) => {
      currentStorageTable.value = 'sub_fields';
      fetch(`/api/storage/data?table=sub_fields&task_id=${encodeURIComponent(storageSearchTaskId.value || '')}`)
        .then(r => r.json())
        .then(data => {
          storageRows.value = data.filter(r => r.main_field_id === mainFieldId);
        });
    };

    // --- 全局配置弹窗 ---
    const loadSystemStatus = async () => {
      try {
        const resp = await fetch('/api/system/status');
        if (resp.ok) {
          sysStatus.value = await resp.json();
          systemConfigForm.value.mongodb_uri = sysStatus.value.mongodb_uri;
          systemConfigForm.value.newapi_url = sysStatus.value.newapi_url;
          systemConfigForm.value.newapi_model = sysStatus.value.newapi_model;
          aiForm.value.api_url = sysStatus.value.newapi_url;
          aiForm.value.model = sysStatus.value.newapi_model;
        }
      } catch (e) {
        console.error(e);
      }
    };

    const saveSystemConfig = async () => {
      try {
        const resp = await fetch('/api/system/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(systemConfigForm.value)
        });
        if (resp.ok) {
          alert('配置已成功保存！');
          showConfigModal.value = false;
          await loadSystemStatus();
        }
      } catch (e) {
        alert(`保存配置失败: ${e.message}`);
      }
    };

    onMounted(async () => {
      generateNewTaskId();
      await loadSystemStatus();
      await fetchTaskList();
      if (taskList.value.length > 0) {
        selectedTaskId.value = taskList.value[0].task_id;
        await loadTaskDetail();
      }
      await fetchStorageData();
    });

    return {
      activeTab,
      sysStatus,
      showConfigModal,
      systemConfigForm,
      saveSystemConfig,
      // 页面 1
      crawlForm,
      isCrawling,
      logs,
      logBox,
      taskList,
      generateNewTaskId,
      fillSampleUrl,
      clearLogs,
      startCrawlTask,
      stopCrawlTask,
      fetchTaskList,
      // 页面 2
      selectedTaskId,
      currentTaskDetail,
      loadTaskDetail,
      renderedMarkdownHtml,
      viewTaskPreview,
      goToExtraction,
      downloadCurrentMd,
      copyMdText,
      // 页面 3
      fieldConfig,
      isAiAccordionOpen,
      aiForm,
      isExtracting,
      extractionResult,
      extractionSaveSummary,
      toggleAiParamAccordion,
      addMainField,
      removeMainField,
      addSubField,
      removeSubField,
      clearFields,
      applyTemplate,
      startAIExtraction,
      copyExtractionJson,
      // 页面 4
      currentStorageTable,
      storageSearchTaskId,
      storageRows,
      currentStorageTableTitle,
      switchStorageTable,
      fetchStorageData,
      filterSubFieldsByMain
    };
  }
}).mount('#app');
