import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const BACKEND_URL = 'http://localhost:8000';

function App() {
  const [baseUrl, setBaseUrl] = useState('https://tighthug.in');
  const [cmdInput, setCmdInput] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [currentStage, setCurrentStage] = useState('idle');
  const [intentData, setIntentData] = useState(null);
  const [registry, setRegistry] = useState(null);
  const [steps, setSteps] = useState([]);
  const [results, setResults] = useState([]);
  const [missingFields, setMissingFields] = useState([]);
  const [logs, setLogs] = useState([]);
  const [timings, setTimings] = useState({});
  const [missingFieldValues, setMissingFieldValues] = useState({});
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [conversationContext, setConversationContext] = useState({
    isLoggedIn: false,
    currentPage: null,
    sessionData: {}
  });
  
  const consoleRef = useRef(null);
  const chatRef = useRef(null);
  const stageStartTime = useRef({});

  const addLog = (text, type = 'info') => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setLogs(prev => {
      const newLogs = [...prev, { time, text, type }];
      return newLogs.slice(-100);
    });
  };

  useEffect(() => {
    if (consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [logs]);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [chatMessages]);

  const recordTiming = (stageName) => {
    if (stageStartTime.current[stageName]) {
      const elapsed = Date.now() - stageStartTime.current[stageName];
      setTimings(prev => ({ ...prev, [stageName]: elapsed }));
    }
  };

  const startTiming = (stageName) => {
    stageStartTime.current[stageName] = Date.now();
  };

  const addChatMessage = (text, sender = 'user', metadata = null) => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setChatMessages(prev => [...prev, { time, text, sender, metadata }]);
  };

  const resetAll = () => {
    setIsRunning(false);
    setCurrentStage('idle');
    setIntentData(null);
    setRegistry(null);
    setSteps([]);
    setResults([]);
    setMissingFields([]);
    setLogs([]);
    setTimings({});
    setMissingFieldValues({});
    setChatMessages([]);
    setConversationContext({ isLoggedIn: false, currentPage: null, sessionData: {} });
    stageStartTime.current = {};
    addLog('System reset', 'info');
  };

  const runPipeline = async (extraParams = null, userMessage = null) => {
    if (isRunning) return;
    
    setIsRunning(true);
    setCurrentStage('input');
    setSteps([]);
    setResults([]);
    setTimings({});
    stageStartTime.current = {};
    
    const userInput = userMessage || cmdInput.trim();
    if (!userInput) {
      setIsRunning(false);
      setCurrentStage('idle');
      return;
    }

    // Add to chat
    addChatMessage(userInput, 'user');
    addLog('Pipeline started', 'info');
    addLog(`Input received: "${userInput}"`, 'info');
    startTiming('input');
    
    const requestBody = {
      user_input: userInput,
      base_url: baseUrl,
      extra_params: extraParams || null
    };

    try {
      // Step 1: Input Capture (already done)
      await new Promise(resolve => setTimeout(resolve, 100));
      recordTiming('input');
      setCurrentStage('intent');
      addLog('Calling qwen2.5:7b for intent parsing...', 'llm');
      startTiming('intent');

      // Step 2: Intent Parsing
      const response = await axios.post(`${BACKEND_URL}/run`, requestBody);
      recordTiming('intent');
      
      // Check for error status from backend
      if (response.data.status === 'error') {
        const errorMsg = response.data.error || 'Backend returned an error';
        const errorDetails = response.data.trace ? `\n\nTrace:\n${response.data.trace}` : '';
        throw new Error(`${errorMsg}${errorDetails}`);
      }
      
      if (response.data.intent_data) {
        setIntentData(response.data.intent_data);
        addLog(`Intent parsed: ${response.data.intent_data.intent}`, 'success');
        setCurrentStage('routing');
        startTiming('routing');
      }

      // Step 3: URL Routing
      await new Promise(resolve => setTimeout(resolve, 50));
      recordTiming('routing');
      if (response.data.registry) {
        addLog(`Routing to ${response.data.registry.url}`, 'info');
        setCurrentStage('inspecting');
        startTiming('inspecting');
      }

      // Step 4: Live Page Inspection
      if (response.data.registry) {
        setRegistry(response.data.registry);
        const fieldCount = response.data.registry.fields?.length || 0;
        addLog(`Field Registry built — ${fieldCount} fields`, 'success');
        recordTiming('inspecting');
        setCurrentStage('checking');
        startTiming('checking');
      }

      // Step 5: Param Check
      if (response.data.status === 'needs_input') {
        setMissingFields(response.data.missing_fields || []);
        setCurrentStage('needs_input');
        recordTiming('checking');
        addLog(`Missing params: ${response.data.missing_fields?.join(', ') || 'unknown'}`, 'warn');
        setIsRunning(false);
        return;
      }
      recordTiming('checking');
      addLog('All required params provided', 'success');

      // Step 6: Step Generation
      if (response.data.steps) {
        setCurrentStage('generating');
        addLog('Calling qwen2.5:7b for step generation...', 'llm');
        startTiming('generating');
        await new Promise(resolve => setTimeout(resolve, 300));
        setSteps(response.data.steps);
        recordTiming('generating');
        addLog(`${response.data.steps.length} steps generated`, 'success');
        setCurrentStage('executing');
        startTiming('executing');
      }

      // Handle query results
      if (response.data.query_result) {
        const queryResult = response.data.query_result;
        recordTiming('executing');
        setCurrentStage('done');
        addLog('Query answered', 'success');
        
        // Display query answer in chat with products
        addChatMessage(queryResult, 'assistant', { 
          type: 'success',
          products: queryResult.products || [],
          items: queryResult.items || []
        });
        setIsRunning(false);
        return;
      }

      // Step 7: Playwright Execution
      if (response.data.results) {
        setResults(response.data.results);
        const successCount = response.data.results.filter(r => r.status === 'ok').length;
        const failCount = response.data.results.filter(r => r.status === 'failed').length;
        recordTiming('executing');
        
        if (response.data.status === 'success') {
          addLog('Pipeline complete', 'success');
          setCurrentStage('done');
          
          // Update conversation context
          if (intentData?.intent === 'signup' || intentData?.intent === 'login') {
            setConversationContext(prev => ({
              ...prev,
              isLoggedIn: true,
              currentPage: registry?.url || baseUrl
            }));
            addChatMessage('Account created and logged in successfully!', 'system', { type: 'success' });
          } else if (intentData?.intent === 'navigate') {
            setConversationContext(prev => ({
              ...prev,
              currentPage: registry?.url || baseUrl
            }));
          }
          
          // Generate response based on intent
          let responseText = 'Task completed successfully.';
          if (intentData?.intent === 'signup') {
            responseText = 'Account created successfully! You are now logged in.';
          } else if (intentData?.intent === 'login') {
            responseText = 'Logged in successfully!';
          } else if (intentData?.intent === 'navigate') {
            responseText = `Navigated to ${registry?.url || 'the page'}.`;
          }
          addChatMessage(responseText, 'assistant', { type: 'success' });
        } else if (response.data.status === 'partial') {
          addLog(`Pipeline partially complete: ${successCount} succeeded, ${failCount} failed`, 'warn');
          setCurrentStage('error');
          addChatMessage(`Task partially completed: ${successCount} succeeded, ${failCount} failed.`, 'assistant', { type: 'warning' });
        }
      }

      setIsRunning(false);
    } catch (error) {
      let errorMsg = error.message;
      if (error.response) {
        // Backend returned an error response
        const backendError = error.response.data?.error || error.response.data?.message || error.message;
        errorMsg = backendError;
        
        // Show detailed error in console
        addLog(`Backend error: ${backendError}`, 'error');
        
        // If it's an Ollama error, show helpful message
        if (backendError.includes('Ollama') || backendError.includes('Cannot connect')) {
          addLog('→ Make sure Ollama is running: ollama serve', 'error');
          addLog('→ Check if model is installed: ollama list', 'error');
        }
        
        if (error.response.data?.trace) {
          console.error('Backend trace:', error.response.data.trace);
          // Show first few lines of trace in console
          const traceLines = error.response.data.trace.split('\n').slice(0, 5);
          traceLines.forEach(line => {
            if (line.strip()) addLog(`  ${line}`, 'error');
          });
        }
      } else if (error.request) {
        // Request was made but no response received
        errorMsg = 'Cannot connect to backend. Make sure the backend is running on http://localhost:8000';
        addLog(`Network error: ${errorMsg}`, 'error');
        addLog('→ Check if backend is running: python start_server.py', 'error');
      } else {
        addLog(`Error: ${errorMsg}`, 'error');
      }
      setCurrentStage('error');
      setIsRunning(false);
      recordTiming('error');
    }
  };

  const handleMissingFieldsSubmit = (e) => {
    e.preventDefault();
    const values = {};
    missingFields.forEach(field => {
      const input = document.querySelector(`#missing-${field.replace(/\s+/g, '-').toLowerCase()}`);
      if (input) {
        values[field] = input.value;
      }
    });
    runPipeline(values);
  };

  const handleChatSend = async () => {
    if (!chatInput.trim() || isRunning) return;
    const message = chatInput.trim();
    setChatInput('');
    await runPipeline(null, message);
  };

  const getStatusBadge = () => {
    const statusMap = {
      idle: { text: 'IDLE', color: '#666' },
      input: { text: 'RUNNING', color: '#00e5ff' },
      intent: { text: 'RUNNING', color: '#00e5ff' },
      routing: { text: 'RUNNING', color: '#00e5ff' },
      inspecting: { text: 'RUNNING', color: '#00e5ff' },
      checking: { text: 'RUNNING', color: '#00e5ff' },
      generating: { text: 'RUNNING', color: '#00e5ff' },
      executing: { text: 'RUNNING', color: '#00e5ff' },
      done: { text: 'COMPLETE', color: '#00ff94' },
      error: { text: 'ERROR', color: '#ff3d6b' },
      needs_input: { text: 'WAITING', color: '#ffb020' }
    };
    return statusMap[currentStage] || statusMap.idle;
  };

  const getStepState = (stepId) => {
    const stageMap = {
      'step-input': ['input'],
      'step-intent': ['intent'],
      'step-routing': ['routing'],
      'step-inspect': ['inspecting'],
      'step-params': ['checking', 'needs_input'],
      'step-generate': ['generating'],
      'step-execute': ['executing']
    };
    
    const activeStages = stageMap[stepId] || [];
    if (activeStages.includes(currentStage)) return 'active';
    if (currentStage === 'done' && stepId === 'step-execute') return 'done';
    if (currentStage === 'error' && stepId === 'step-execute') return 'error';
    if (['done', 'error', 'needs_input'].includes(currentStage)) {
      const stepOrder = ['step-input', 'step-intent', 'step-routing', 'step-inspect', 'step-params', 'step-generate', 'step-execute'];
      const currentIndex = stepOrder.indexOf(stepId);
      const doneIndex = stepOrder.findIndex(s => activeStages.some(as => {
        const map = {
          'input': 'step-input',
          'intent': 'step-intent',
          'routing': 'step-routing',
          'inspecting': 'step-inspect',
          'checking': 'step-params',
          'generating': 'step-generate',
          'executing': 'step-execute'
        };
        return map[as] === s;
      }));
      if (currentIndex <= doneIndex) return 'done';
    }
    return 'pending';
  };

  const clearConsole = () => {
    setLogs([]);
    addLog('Console cleared', 'info');
  };

  const renderJSON = (obj) => {
    const jsonStr = JSON.stringify(obj, null, 2);
    return jsonStr.split('\n').map((line, lineIdx) => {
      const parts = [];
      let keyMatch = line.match(/^(\s*)("([^"]+)":\s*)/);
      if (keyMatch) {
        parts.push(<span key={`indent-${lineIdx}`}>{keyMatch[1]}</span>);
        parts.push(<span key={`key-${lineIdx}`} className="json-key">{keyMatch[2]}</span>);
        const rest = line.substring(keyMatch[0].length);
        if (rest.trim().startsWith('"')) {
          const strMatch = rest.match(/^("([^"]+)")/);
          if (strMatch) {
            parts.push(<span key={`str-${lineIdx}`} className="json-string">{strMatch[1]}</span>);
            parts.push(<span key={`rest-${lineIdx}`}>{rest.substring(strMatch[0].length)}</span>);
          } else {
            parts.push(<span key={`rest-${lineIdx}`}>{rest}</span>);
          }
        } else if (rest.trim() === 'null') {
          parts.push(<span key={`null-${lineIdx}`} className="json-null">null</span>);
        } else {
          parts.push(<span key={`rest-${lineIdx}`}>{rest}</span>);
        }
      } else {
        parts.push(<span key={`line-${lineIdx}`}>{line}</span>);
      }
      return <div key={lineIdx}>{parts}</div>;
    });
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Syne:wght@600;700&display=swap');
        
        * {
          margin: 0;
          padding: 0;
          box-sizing: border-box;
        }
        
        body {
          font-family: 'JetBrains Mono', monospace;
          background: #07090f;
          color: #e0e0e0;
          overflow-x: hidden;
        }
        
        .app {
          min-height: 100vh;
          background: 
            linear-gradient(rgba(0, 229, 255, 0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 229, 255, 0.03) 1px, transparent 1px);
          background-size: 20px 20px;
        }
        
        .header {
          padding: 16px 24px;
          border-bottom: 1px solid rgba(0, 229, 255, 0.2);
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: rgba(7, 9, 15, 0.8);
          backdrop-filter: blur(10px);
        }
        
        .logo {
          font-family: 'Syne', sans-serif;
          font-size: 24px;
          font-weight: 700;
          color: #00e5ff;
          letter-spacing: 2px;
        }
        
        .status-badge {
          padding: 6px 12px;
          border: 1px solid;
          border-radius: 4px;
          font-size: 11px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 1px;
        }
        
        .version {
          font-size: 11px;
          color: #666;
          letter-spacing: 1px;
        }
        
        .container {
          display: flex;
          gap: 20px;
          padding: 20px;
          max-width: 1920px;
          margin: 0 auto;
        }
        
        .left-column {
          flex: 0 0 60%;
          display: flex;
          flex-direction: column;
          gap: 20px;
        }
        
        .right-column {
          flex: 0 0 40%;
          display: flex;
          flex-direction: column;
          gap: 20px;
        }
        
        .input-section {
          background: rgba(15, 20, 30, 0.6);
          border: 1px solid rgba(0, 229, 255, 0.2);
          border-radius: 8px;
          padding: 20px;
        }
        
        .input-row {
          display: flex;
          gap: 12px;
          margin-bottom: 12px;
        }
        
        .input-group {
          flex: 1;
        }
        
        .input-label {
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 1px;
          color: #00e5ff;
          margin-bottom: 6px;
          font-weight: 600;
        }
        
        .input-field {
          width: 100%;
          padding: 10px 12px;
          background: rgba(0, 0, 0, 0.4);
          border: 1px solid rgba(0, 229, 255, 0.3);
          border-radius: 4px;
          color: #e0e0e0;
          font-family: 'JetBrains Mono', monospace;
          font-size: 13px;
        }
        
        .input-field:focus {
          outline: none;
          border-color: #00e5ff;
          box-shadow: 0 0 10px rgba(0, 229, 255, 0.3);
        }
        
        .button-group {
          display: flex;
          gap: 10px;
          margin-top: 12px;
        }
        
        .btn {
          padding: 10px 20px;
          border: 1px solid;
          border-radius: 4px;
          font-family: 'JetBrains Mono', monospace;
          font-size: 12px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 1px;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .btn-primary {
          background: transparent;
          border-color: #00e5ff;
          color: #00e5ff;
        }
        
        .btn-primary:hover:not(:disabled) {
          background: rgba(0, 229, 255, 0.1);
          box-shadow: 0 0 15px rgba(0, 229, 255, 0.4);
        }
        
        .btn-primary:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }
        
        .btn-secondary {
          background: transparent;
          border-color: #666;
          color: #666;
        }
        
        .btn-secondary:hover {
          border-color: #999;
          color: #999;
        }
        
        .pipeline-container {
          position: relative;
        }
        
        .spine {
          position: absolute;
          left: 20px;
          top: 0;
          bottom: 0;
          width: 2px;
          background: rgba(0, 229, 255, 0.2);
        }
        
        .spine-segment {
          height: 100px;
          background: rgba(0, 255, 148, 0.6);
          transition: height 0.3s;
        }
        
        .spine-active {
          background: linear-gradient(180deg, #00e5ff, #00ff94);
          animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
          0%, 100% { opacity: 0.6; }
          50% { opacity: 1; }
        }
        
        .step-card {
          position: relative;
          background: rgba(15, 20, 30, 0.6);
          border: 1px solid;
          border-radius: 8px;
          padding: 16px;
          margin-bottom: 16px;
          transition: all 0.3s;
        }
        
        .step-card.pending {
          opacity: 0.3;
          border-color: rgba(0, 229, 255, 0.1);
        }
        
        .step-card.active {
          opacity: 1;
          border-color: #00e5ff;
          box-shadow: 0 0 20px rgba(0, 229, 255, 0.3);
          animation: scanline 3s infinite;
        }
        
        .step-card.done {
          opacity: 1;
          border-color: #00ff94;
        }
        
        .step-card.error {
          opacity: 1;
          border-color: #ff3d6b;
        }
        
        @keyframes scanline {
          0% { background-position: 0 0; }
          100% { background-position: 0 100%; }
        }
        
        .step-header {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 12px;
        }
        
        .step-number {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 600;
          font-size: 14px;
          border: 2px solid;
        }
        
        .step-number.pending {
          border-color: #666;
          color: #666;
        }
        
        .step-number.active {
          border-color: #00e5ff;
          color: #00e5ff;
          box-shadow: 0 0 15px rgba(0, 229, 255, 0.5);
        }
        
        .step-number.done {
          border-color: #00ff94;
          color: #00ff94;
        }
        
        .step-number.error {
          border-color: #ff3d6b;
          color: #ff3d6b;
        }
        
        .step-title {
          flex: 1;
          font-family: 'Syne', sans-serif;
          font-size: 16px;
          font-weight: 600;
          color: #e0e0e0;
        }
        
        .step-tag {
          padding: 4px 8px;
          border-radius: 4px;
          font-size: 10px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        
        .step-description {
          font-size: 11px;
          color: #999;
          margin-bottom: 12px;
          line-height: 1.5;
        }
        
        .step-content {
          margin-top: 12px;
        }
        
        .data-block {
          background: rgba(0, 0, 0, 0.4);
          border: 1px solid rgba(0, 229, 255, 0.2);
          border-radius: 4px;
          padding: 12px;
          font-family: 'JetBrains Mono', monospace;
          font-size: 12px;
          white-space: pre-wrap;
          word-break: break-all;
        }
        
        .data-block.locked {
          border-color: #00ff94;
        }
        
        .json-key {
          color: #00e5ff;
        }
        
        .json-string {
          color: #ffb020;
        }
        
        .json-null {
          color: #666;
        }
        
        .loading-spinner {
          display: inline-block;
          width: 12px;
          height: 12px;
          border: 2px solid rgba(0, 229, 255, 0.3);
          border-top-color: #00e5ff;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }
        
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        
        .field-chips {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 8px;
        }
        
        .field-chip {
          padding: 6px 10px;
          border: 1px solid;
          border-radius: 4px;
          font-size: 11px;
          background: rgba(0, 0, 0, 0.3);
        }
        
        .field-chip.required {
          border-color: #00e5ff;
          color: #00e5ff;
        }
        
        .field-chip.optional {
          border-color: #666;
          color: #666;
        }
        
        .field-selector {
          font-size: 9px;
          color: #666;
          margin-top: 2px;
          font-family: 'JetBrains Mono', monospace;
        }
        
        .params-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 11px;
          margin-top: 8px;
        }
        
        .params-table th,
        .params-table td {
          padding: 8px;
          text-align: left;
          border-bottom: 1px solid rgba(0, 229, 255, 0.1);
        }
        
        .params-table th {
          color: #00e5ff;
          font-weight: 600;
          text-transform: uppercase;
          font-size: 10px;
        }
        
        .status-check {
          color: #00ff94;
        }
        
        .status-cross {
          color: #ff3d6b;
        }
        
        .missing-form {
          margin-top: 12px;
          padding: 12px;
          background: rgba(255, 176, 32, 0.1);
          border: 1px solid rgba(255, 176, 32, 0.3);
          border-radius: 4px;
        }
        
        .missing-form input {
          width: 100%;
          padding: 8px;
          margin-bottom: 8px;
          background: rgba(0, 0, 0, 0.4);
          border: 1px solid rgba(255, 176, 32, 0.3);
          border-radius: 4px;
          color: #e0e0e0;
          font-family: 'JetBrains Mono', monospace;
          font-size: 12px;
        }
        
        .steps-list {
          margin-top: 8px;
        }
        
        .step-row {
          display: grid;
          grid-template-columns: 80px 1fr 200px;
          gap: 12px;
          padding: 8px;
          margin-bottom: 4px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 4px;
          font-size: 11px;
          align-items: center;
        }
        
        .step-row.active {
          background: rgba(0, 229, 255, 0.2);
          animation: pulse-bg 1.5s infinite;
        }
        
        .step-row.complete {
          background: rgba(0, 255, 148, 0.1);
        }
        
        .step-row.failed {
          background: rgba(255, 61, 107, 0.1);
        }
        
        @keyframes pulse-bg {
          0%, 100% { opacity: 0.2; }
          50% { opacity: 0.4; }
        }
        
        .step-action {
          color: #b794f6;
          font-weight: 600;
        }
        
        .step-selector {
          color: #00e5ff;
          font-family: 'JetBrains Mono', monospace;
        }
        
        .step-value {
          color: #ffb020;
          font-family: 'JetBrains Mono', monospace;
        }
        
        .progress-bar {
          width: 100%;
          height: 4px;
          background: rgba(0, 229, 255, 0.1);
          border-radius: 2px;
          margin-top: 12px;
          overflow: hidden;
        }
        
        .progress-fill {
          height: 100%;
          background: linear-gradient(90deg, #00e5ff, #00ff94);
          transition: width 0.3s;
        }
        
        .card {
          background: rgba(15, 20, 30, 0.6);
          border: 1px solid rgba(0, 229, 255, 0.2);
          border-radius: 8px;
          padding: 16px;
        }
        
        .card-title {
          font-family: 'Syne', sans-serif;
          font-size: 14px;
          font-weight: 600;
          color: #00e5ff;
          margin-bottom: 12px;
          text-transform: uppercase;
          letter-spacing: 1px;
        }
        
        .output-row {
          display: flex;
          justify-content: space-between;
          padding: 6px 0;
          border-bottom: 1px solid rgba(0, 229, 255, 0.1);
          font-size: 11px;
        }
        
        .output-key {
          color: #00e5ff;
          font-weight: 600;
        }
        
        .output-value {
          color: #e0e0e0;
          font-family: 'JetBrains Mono', monospace;
        }
        
        .console {
          max-height: 400px;
          overflow-y: auto;
          font-family: 'JetBrains Mono', monospace;
          font-size: 11px;
          background: rgba(0, 0, 0, 0.4);
          border: 1px solid rgba(0, 229, 255, 0.2);
          border-radius: 4px;
          padding: 12px;
        }
        
        .console-line {
          margin-bottom: 4px;
          line-height: 1.4;
        }
        
        .console-time {
          color: #666;
          margin-right: 8px;
        }
        
        .console-info {
          color: #999;
        }
        
        .console-success {
          color: #00ff94;
        }
        
        .console-warn {
          color: #ffb020;
        }
        
        .console-error {
          color: #ff3d6b;
        }
        
        .console-llm {
          color: #00e5ff;
        }
        
        .timing-row {
          display: flex;
          justify-content: space-between;
          padding: 6px 0;
          border-bottom: 1px solid rgba(0, 229, 255, 0.1);
          font-size: 11px;
        }
        
        .timing-value {
          color: #ffb020;
          font-family: 'JetBrains Mono', monospace;
        }
        
        .chat-messages {
          max-height: 300px;
          overflow-y: auto;
          font-family: 'JetBrains Mono', monospace;
          font-size: 11px;
          padding: 8px;
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid rgba(0, 229, 255, 0.2);
          border-radius: 4px;
        }
        
        .chat-message {
          margin-bottom: 12px;
          padding: 8px;
          border-radius: 4px;
          background: rgba(0, 0, 0, 0.2);
        }
        
        .chat-message.chat-user {
          border-left: 2px solid #00e5ff;
          background: rgba(0, 229, 255, 0.1);
        }
        
        .chat-message.chat-assistant {
          border-left: 2px solid #00ff94;
          background: rgba(0, 255, 148, 0.1);
        }
        
        .chat-message.chat-system {
          border-left: 2px solid #ffb020;
          background: rgba(255, 176, 32, 0.1);
        }
        
        .chat-message-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 4px;
          font-size: 9px;
        }
        
        .chat-time {
          color: #666;
        }
        
        .chat-sender {
          color: #00e5ff;
          font-weight: 600;
          text-transform: uppercase;
        }
        
        .chat-message-text {
          color: #e0e0e0;
          line-height: 1.4;
          word-wrap: break-word;
        }
        
        .chat-input-container {
          display: flex;
          gap: 8px;
          align-items: center;
        }
        
        .chat-input {
          flex: 1;
          padding: 8px 12px;
          background: rgba(0, 0, 0, 0.4);
          border: 1px solid rgba(0, 229, 255, 0.3);
          border-radius: 4px;
          color: #e0e0e0;
          font-family: 'JetBrains Mono', monospace;
          font-size: 12px;
        }
        
        .chat-input:focus {
          outline: none;
          border-color: #00e5ff;
          box-shadow: 0 0 10px rgba(0, 229, 255, 0.3);
        }
        
        .chat-input:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
      `}</style>

      <div className="app">
        <div className="header">
          <div className="logo">NINA</div>
          <div className="status-badge" style={{ borderColor: getStatusBadge().color, color: getStatusBadge().color }}>
            {getStatusBadge().text}
          </div>
          <div className="version">v1.0.0</div>
        </div>

        <div className="container">
          <div className="left-column">
            <div className="input-section">
              <div className="input-row">
                <div className="input-group">
                  <div className="input-label">TARGET URL</div>
                  <input
                    type="text"
                    className="input-field"
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    placeholder="https://example.com"
                  />
                </div>
                <div className="input-group">
                  <div className="input-label">COMMAND</div>
                  <input
                    type="text"
                    className="input-field"
                    value={cmdInput}
                    onChange={(e) => setCmdInput(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && !isRunning && runPipeline()}
                    placeholder="e.g. Create an account with raju@gmail.com and password Asdf@1234"
                  />
                </div>
              </div>
              <div className="button-group">
                <button
                  className="btn btn-primary"
                  onClick={() => runPipeline()}
                  disabled={isRunning}
                >
                  RUN
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={resetAll}
                  disabled={isRunning}
                >
                  RESET
                </button>
              </div>
            </div>

            <div className="pipeline-container">
              <div className="spine">
                {['step-input', 'step-intent', 'step-routing', 'step-inspect', 'step-params', 'step-generate', 'step-execute'].map((stepId, idx) => {
                  const state = getStepState(stepId);
                  const isActive = state === 'active';
                  const isDone = state === 'done';
                  return (
                    <div
                      key={stepId}
                      className={`spine-segment ${isActive ? 'spine-active' : ''}`}
                      style={{
                        height: isDone || isActive ? '100px' : '0',
                        marginTop: idx * 116
                      }}
                    />
                  );
                })}
              </div>

              {/* Step 1: Input Capture */}
              <div className={`step-card ${getStepState('step-input')}`}>
                <div className="step-header">
                  <div className={`step-number ${getStepState('step-input')}`}>1</div>
                  <div className="step-title">Input Capture</div>
                  <div className="step-tag" style={{ background: 'rgba(0, 229, 255, 0.2)', color: '#00e5ff' }}>USER</div>
                </div>
                <div className="step-description">Raw command text received. Voice or typed. Only text is transmitted — no audio.</div>
                {currentStage !== 'idle' && (
                  <div className="step-content">
                    <div className={`data-block ${getStepState('step-input') === 'done' ? 'locked' : ''}`}>
                      <span className="json-key">user_input:</span> <span className="json-string">"{cmdInput}"</span>{'\n'}
                      <span className="json-key">base_url:</span> <span className="json-string">"{baseUrl}"</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Step 2: Intent Parsing */}
              <div className={`step-card ${getStepState('step-intent')}`}>
                <div className="step-header">
                  <div className={`step-number ${getStepState('step-intent')}`}>2</div>
                  <div className="step-title">Intent Parsing</div>
                  <div className="step-tag" style={{ background: 'rgba(255, 176, 32, 0.2)', color: '#ffb020' }}>LLM · qwen2.5:7b</div>
                </div>
                <div className="step-description">Qwen2.5:7b extracts intent and params. Prompt ~200 tokens. temp=0.1, max=512.</div>
                {currentStage === 'intent' && (
                  <div className="step-content">
                    <div className="loading-spinner" style={{ marginRight: '8px' }}></div>
                    <span style={{ color: '#00e5ff' }}>Waiting for LLM response...</span>
                  </div>
                )}
                {intentData && (
                  <div className="step-content">
                    <div className={`data-block ${getStepState('step-intent') === 'done' ? 'locked' : ''}`}>
                      {renderJSON(intentData)}
                    </div>
                  </div>
                )}
              </div>

              {/* Step 3: URL Routing */}
              <div className={`step-card ${getStepState('step-routing')}`}>
                <div className="step-header">
                  <div className={`step-number ${getStepState('step-routing')}`}>3</div>
                  <div className="step-title">URL Routing</div>
                  <div className="step-tag" style={{ background: 'rgba(183, 148, 246, 0.2)', color: '#b794f6' }}>NO LLM</div>
                </div>
                <div className="step-description">Action Graph dict lookup. intent → target URL. Instant, no model call.</div>
                {registry && (
                  <div className="step-content">
                    <div className={`data-block ${getStepState('step-routing') === 'done' ? 'locked' : ''}`}>
                      <span className="json-key">target_url:</span> <span className="json-string">"{registry.url}"</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Step 4: Live Page Inspection */}
              <div className={`step-card ${getStepState('step-inspect')}`}>
                <div className="step-header">
                  <div className={`step-number ${getStepState('step-inspect')}`}>4</div>
                  <div className="step-title">Live Page Inspection</div>
                  <div className="step-tag" style={{ background: 'rgba(0, 255, 148, 0.2)', color: '#00ff94' }}>PLAYWRIGHT</div>
                </div>
                <div className="step-description">Playwright navigates to target URL. Reads live DOM via accessibility tree. Builds Field Registry.</div>
                {currentStage === 'inspecting' && (
                  <div className="step-content">
                    <div className="loading-spinner" style={{ marginRight: '8px' }}></div>
                    <span style={{ color: '#00e5ff' }}>Building field registry...</span>
                  </div>
                )}
                {registry && registry.fields && (
                  <div className="step-content">
                    <div style={{ marginBottom: '8px', color: '#00ff94', fontSize: '11px' }}>
                      {registry.fields.length} fields found
                    </div>
                    <div className="field-chips">
                      {registry.fields.map((field, idx) => (
                        <div key={idx} className={`field-chip ${field.required ? 'required' : 'optional'}`}>
                          <div>{field.semanticName}</div>
                          <div className="field-selector">{field.selector}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Step 5: Param Check */}
              <div className={`step-card ${getStepState('step-params')}`}>
                <div className="step-header">
                  <div className={`step-number ${getStepState('step-params')}`}>5</div>
                  <div className="step-title">Param Check</div>
                  <div className="step-tag" style={{ background: 'rgba(183, 148, 246, 0.2)', color: '#b794f6' }}>NO LLM</div>
                </div>
                <div className="step-description">Required fields compared against provided params. Missing = pipeline pauses and asks user.</div>
                {registry && registry.fields && intentData && (
                  <div className="step-content">
                    <table className="params-table">
                      <thead>
                        <tr>
                          <th>Field</th>
                          <th>Required</th>
                          <th>Provided</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {registry.fields.filter(f => f.type !== 'submit' && f.type !== 'button' && f.type !== 'checkbox').map((field, idx) => {
                          const hasValue = intentData.params && Object.values(intentData.params).some(v => v !== null);
                          const matched = field.required ? hasValue : true;
                          return (
                            <tr key={idx}>
                              <td>{field.semanticName}</td>
                              <td>{field.required ? 'Yes' : 'No'}</td>
                              <td>{hasValue ? 'Yes' : 'No'}</td>
                              <td>{matched ? <span className="status-check">✓</span> : <span className="status-cross">✕</span>}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {currentStage === 'needs_input' && missingFields.length > 0 && (
                      <form className="missing-form" onSubmit={handleMissingFieldsSubmit}>
                        <div style={{ marginBottom: '8px', color: '#ffb020', fontSize: '11px', fontWeight: '600' }}>
                          Missing required fields:
                        </div>
                        {missingFields.map((field, idx) => (
                          <input
                            key={idx}
                            id={`missing-${field.replace(/\s+/g, '-').toLowerCase()}`}
                            type="text"
                            placeholder={field}
                            required
                          />
                        ))}
                        <button type="submit" className="btn btn-primary" style={{ marginTop: '8px' }}>
                          Continue
                        </button>
                      </form>
                    )}
                  </div>
                )}
              </div>

              {/* Step 6: Step Generation */}
              <div className={`step-card ${getStepState('step-generate')}`}>
                <div className="step-header">
                  <div className={`step-number ${getStepState('step-generate')}`}>6</div>
                  <div className="step-title">Step Generation</div>
                  <div className="step-tag" style={{ background: 'rgba(255, 176, 32, 0.2)', color: '#ffb020' }}>LLM · qwen2.5:7b</div>
                </div>
                <div className="step-description">Qwen2.5:7b receives the Field Registry and generates browser steps. Prompt ~400 tokens.</div>
                {currentStage === 'generating' && (
                  <div className="step-content">
                    <div className="loading-spinner" style={{ marginRight: '8px' }}></div>
                    <span style={{ color: '#00e5ff' }}>Generating steps...</span>
                  </div>
                )}
                {steps.length > 0 && (
                  <div className="step-content">
                    <div style={{ marginBottom: '8px', color: '#00ff94', fontSize: '11px' }}>
                      {steps.length} steps generated
                    </div>
                    <div className="steps-list">
                      {steps.map((step, idx) => (
                        <div key={idx} className="step-row">
                          <span className="step-action">{step.action}</span>
                          <span className="step-selector">{step.selector || step.url || '-'}</span>
                          {step.value && <span className="step-value">{step.value}</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Step 7: Playwright Execution */}
              <div className={`step-card ${getStepState('step-execute')}`}>
                <div className="step-header">
                  <div className={`step-number ${getStepState('step-execute')}`}>7</div>
                  <div className="step-title">Playwright Execution</div>
                  <div className="step-tag" style={{ background: 'rgba(0, 255, 148, 0.2)', color: '#00ff94' }}>PLAYWRIGHT</div>
                </div>
                <div className="step-description">Steps executed one by one in a real browser. Each waits for selector before acting.</div>
                {results.length > 0 && (
                  <div className="step-content">
                    <div className="steps-list">
                      {results.map((result, idx) => {
                        const step = steps[idx];
                        const isActive = currentStage === 'executing' && idx === results.findIndex(r => r.status !== 'ok');
                        const isComplete = result.status === 'ok';
                        const isFailed = result.status === 'failed';
                        return (
                          <div key={idx} className={`step-row ${isActive ? 'active' : isComplete ? 'complete' : isFailed ? 'failed' : ''}`}>
                            <span className="step-action">
                              {step?.action || 'unknown'}
                              {isComplete && <span style={{ marginLeft: '8px', color: '#00ff94' }}>✓</span>}
                              {isFailed && <span style={{ marginLeft: '8px', color: '#ff3d6b' }}>✕</span>}
                            </span>
                            <span className="step-selector">{step?.selector || step?.url || '-'}</span>
                            {step?.value && <span className="step-value">{step.value}</span>}
                            {isFailed && result.error && (
                              <div style={{ gridColumn: '1 / -1', marginTop: '4px', color: '#ff3d6b', fontSize: '10px' }}>
                                {result.error}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                    <div className="progress-bar">
                      <div
                        className="progress-fill"
                        style={{
                          width: `${(results.filter(r => r.status === 'ok').length / results.length) * 100}%`
                        }}
                      />
                    </div>
                    <div style={{ marginTop: '8px', color: '#00ff94', fontSize: '11px' }}>
                      {results.filter(r => r.status === 'ok').length} / {results.length} steps completed
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="right-column">
            <div className="card" style={{ maxHeight: '400px', display: 'flex', flexDirection: 'column' }}>
              <div className="card-title">CHAT</div>
              <div className="chat-messages" ref={chatRef} style={{ flex: 1, overflowY: 'auto', marginBottom: '12px' }}>
                {chatMessages.length === 0 && (
                  <div style={{ color: '#666', fontSize: '11px', fontStyle: 'italic', padding: '8px' }}>
                    Start a conversation... Try: "create an account" or "what's available?"
                  </div>
                )}
                {chatMessages.map((msg, idx) => (
                  <div key={idx} className={`chat-message chat-${msg.sender}`}>
                    <div className="chat-message-header">
                      <span className="chat-time">{msg.time}</span>
                      <span className="chat-sender">{msg.sender === 'user' ? 'You' : msg.sender === 'system' ? 'System' : 'Nina'}</span>
                    </div>
                    {typeof msg.text === 'string' ? (
                      <div className="chat-message-text">{msg.text}</div>
                    ) : (
                      <div className="chat-message-text">
                        {msg.text?.answer || 'No answer provided.'}
                        {msg.text?.items && msg.text.items.length > 0 && (
                          <div style={{ marginTop: '8px' }}>
                            {msg.text.items.map((item, i) => (
                              <div key={i} style={{ fontSize: '10px', color: '#00e5ff', marginTop: '4px' }}>• {item}</div>
                            ))}
                          </div>
                        )}
                        {msg.text?.products && msg.text.products.length > 0 && (
                          <div style={{ marginTop: '12px', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: '8px' }}>
                            {msg.text.products.map((product, i) => (
                              <div 
                                key={i} 
                                className="product-card"
                                style={{
                                  border: '1px solid rgba(0, 229, 255, 0.3)',
                                  borderRadius: '4px',
                                  padding: '8px',
                                  background: 'rgba(0, 0, 0, 0.3)',
                                  cursor: 'pointer',
                                  transition: 'all 0.2s'
                                }}
                                onClick={() => {
                                  setChatInput(`I want to see more about ${product.name || `product ${i + 1}`}`);
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.borderColor = '#00e5ff';
                                  e.currentTarget.style.background = 'rgba(0, 229, 255, 0.1)';
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.borderColor = 'rgba(0, 229, 255, 0.3)';
                                  e.currentTarget.style.background = 'rgba(0, 0, 0, 0.3)';
                                }}
                              >
                                {product.image && (
                                  <img 
                                    src={product.image.startsWith('http') ? product.image : `${baseUrl}${product.image}`}
                                    alt={product.name || 'Product'}
                                    style={{
                                      width: '100%',
                                      height: '80px',
                                      objectFit: 'cover',
                                      borderRadius: '2px',
                                      marginBottom: '4px'
                                    }}
                                    onError={(e) => {
                                      e.target.style.display = 'none';
                                    }}
                                  />
                                )}
                                <div style={{ fontSize: '9px', color: '#e0e0e0', fontWeight: '600', marginBottom: '2px' }}>
                                  {i + 1}. {product.name || 'Product'}
                                </div>
                                {product.price && (
                                  <div style={{ fontSize: '8px', color: '#00ff94' }}>{product.price}</div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                    {msg.metadata && msg.metadata.type === 'success' && (
                      <div style={{ fontSize: '9px', color: '#00ff94', marginTop: '4px' }}>✓ Success</div>
                    )}
                  </div>
                ))}
              </div>
              <div className="chat-input-container">
                <input
                  type="text"
                  className="chat-input"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyPress={(e) => {
                    if (e.key === 'Enter' && !isRunning && chatInput.trim()) {
                      handleChatSend();
                    }
                  }}
                  placeholder="Type your command..."
                  disabled={isRunning}
                />
                <button
                  className="btn btn-primary"
                  onClick={handleChatSend}
                  disabled={isRunning || !chatInput.trim()}
                  style={{ marginLeft: '8px', padding: '8px 16px' }}
                >
                  Send
                </button>
              </div>
            </div>

            <div className="card">
              <div className="card-title">LIVE OUTPUT</div>
              <div className="output-row">
                <span className="output-key">Intent:</span>
                <span className="output-value">{intentData?.intent || '-'}</span>
              </div>
              <div className="output-row">
                <span className="output-key">Email:</span>
                <span className="output-value">{intentData?.params?.email || 'null'}</span>
              </div>
              <div className="output-row">
                <span className="output-key">Password:</span>
                <span className="output-value">{intentData?.params?.password ? '••••••••' : 'null'}</span>
              </div>
              <div className="output-row">
                <span className="output-key">Name:</span>
                <span className="output-value">{intentData?.params?.name || 'null'}</span>
              </div>
              <div className="output-row">
                <span className="output-key">Target URL:</span>
                <span className="output-value">{registry?.url || '-'}</span>
              </div>
            </div>

            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <div className="card-title">CONSOLE</div>
                <button className="btn btn-secondary" onClick={clearConsole} style={{ padding: '4px 8px', fontSize: '10px' }}>
                  CLEAR
                </button>
              </div>
              <div className="console" ref={consoleRef}>
                {logs.map((log, idx) => (
                  <div key={idx} className={`console-line console-${log.type}`}>
                    <span className="console-time">{log.time}</span>
                    {log.text}
                  </div>
                ))}
              </div>
            </div>

            <div className="card">
              <div className="card-title">SYSTEM SITEMAP</div>
              <div style={{ fontSize: '10px', lineHeight: '1.6', fontFamily: 'JetBrains Mono, monospace' }}>
                <div style={{ marginBottom: '12px', color: '#00e5ff', fontWeight: '600' }}>Data Flow Pipeline:</div>
                
                <div style={{ marginBottom: '8px', paddingLeft: '8px', borderLeft: '2px solid rgba(0, 229, 255, 0.3)' }}>
                  <div style={{ color: '#00ff94', marginBottom: '4px' }}>1. USER INPUT</div>
                  <div style={{ color: '#999', fontSize: '9px', marginLeft: '12px' }}>
                    {cmdInput || '(empty)'} → FastAPI /run
                  </div>
                </div>

                <div style={{ marginBottom: '8px', paddingLeft: '8px', borderLeft: '2px solid rgba(0, 229, 255, 0.3)' }}>
                  <div style={{ color: '#ffb020', marginBottom: '4px' }}>2. INTENT PARSER</div>
                  <div style={{ color: '#999', fontSize: '9px', marginLeft: '12px' }}>
                    ollama_client.py → Ollama (qwen2.5:7b)<br/>
                    {intentData ? (
                      <>
                        <span style={{ color: '#00e5ff' }}>Intent:</span> <span style={{ color: '#ffb020' }}>{intentData.intent}</span><br/>
                        <span style={{ color: '#00e5ff' }}>Params:</span> {JSON.stringify(intentData.params)}
                      </>
                    ) : '(pending)'}
                  </div>
                </div>

                <div style={{ marginBottom: '8px', paddingLeft: '8px', borderLeft: '2px solid rgba(0, 229, 255, 0.3)' }}>
                  <div style={{ color: '#b794f6', marginBottom: '4px' }}>3. ACTION GRAPH</div>
                  <div style={{ color: '#999', fontSize: '9px', marginLeft: '12px' }}>
                    action_graph.py → dict lookup<br/>
                    {intentData ? (
                      <span style={{ color: '#00ff94' }}>→ {baseUrl.replace(/\/$/, '') + (intentData.intent === 'signup' ? '/signup' : intentData.intent === 'login' ? '/login' : '/')}</span>
                    ) : '(pending)'}
                  </div>
                </div>

                <div style={{ marginBottom: '8px', paddingLeft: '8px', borderLeft: '2px solid rgba(0, 229, 255, 0.3)' }}>
                  <div style={{ color: '#00ff94', marginBottom: '4px' }}>4. PLAYWRIGHT NAVIGATION</div>
                  <div style={{ color: '#999', fontSize: '9px', marginLeft: '12px' }}>
                    executor.py → page.goto()<br/>
                    {registry ? (
                      <span style={{ color: '#00ff94' }}>→ Loaded: {registry.url}</span>
                    ) : '(pending)'}
                  </div>
                </div>

                <div style={{ marginBottom: '8px', paddingLeft: '8px', borderLeft: '2px solid rgba(0, 229, 255, 0.3)' }}>
                  <div style={{ color: '#00ff94', marginBottom: '4px' }}>5. FIELD REGISTRY</div>
                  <div style={{ color: '#999', fontSize: '9px', marginLeft: '12px' }}>
                    field_registry.py → Live DOM scan<br/>
                    {registry ? (
                      <>
                        <span style={{ color: '#00e5ff' }}>Fields found:</span> <span style={{ color: '#00ff94' }}>{registry.fields?.length || 0}</span><br/>
                        <span style={{ color: '#666', fontSize: '8px' }}>
                          Selectors: name → id → aria-label → placeholder
                        </span>
                      </>
                    ) : '(pending)'}
                  </div>
                </div>

                <div style={{ marginBottom: '8px', paddingLeft: '8px', borderLeft: '2px solid rgba(0, 229, 255, 0.3)' }}>
                  <div style={{ color: '#ffb020', marginBottom: '4px' }}>6. STEP GENERATOR</div>
                  <div style={{ color: '#999', fontSize: '9px', marginLeft: '12px' }}>
                    step_generator.py → Ollama (qwen2.5:7b)<br/>
                    {steps.length > 0 ? (
                      <>
                        <span style={{ color: '#00e5ff' }}>Steps:</span> <span style={{ color: '#00ff94' }}>{steps.length}</span><br/>
                        <span style={{ color: '#666', fontSize: '8px' }}>
                          Actions: {steps.map(s => s.action).join(', ')}
                        </span>
                      </>
                    ) : '(pending)'}
                  </div>
                </div>

                <div style={{ marginBottom: '8px', paddingLeft: '8px', borderLeft: '2px solid rgba(0, 229, 255, 0.3)' }}>
                  <div style={{ color: '#00ff94', marginBottom: '4px' }}>7. EXECUTOR</div>
                  <div style={{ color: '#999', fontSize: '9px', marginLeft: '12px' }}>
                    executor.py → Playwright actions<br/>
                    {results.length > 0 ? (
                      <>
                        <span style={{ color: '#00e5ff' }}>Completed:</span> <span style={{ color: '#00ff94' }}>
                          {results.filter(r => r.status === 'ok').length}/{results.length}
                        </span>
                      </>
                    ) : '(pending)'}
                  </div>
                </div>

                <div style={{ marginTop: '12px', padding: '8px', background: 'rgba(0, 0, 0, 0.3)', borderRadius: '4px', fontSize: '9px' }}>
                  <div style={{ color: '#00e5ff', marginBottom: '4px', fontWeight: '600' }}>Storage:</div>
                  <div style={{ color: '#999' }}>
                    • Intent Data: {intentData ? '✓' : '✗'}<br/>
                    • Field Registry: {registry ? `✓ (${registry.fields?.length || 0} fields)` : '✗'}<br/>
                    • Generated Steps: {steps.length > 0 ? `✓ (${steps.length} steps)` : '✗'}<br/>
                    • Execution Results: {results.length > 0 ? `✓ (${results.filter(r => r.status === 'ok').length} success)` : '✗'}
                  </div>
                </div>
              </div>
            </div>

            {Object.keys(timings).length > 0 && (
              <div className="card">
                <div className="card-title">TIMING</div>
                {Object.entries(timings).map(([stage, time]) => (
                  <div key={stage} className="timing-row">
                    <span>{stage}</span>
                    <span className="timing-value">{time}ms</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

export default App;

