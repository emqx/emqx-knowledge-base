<template>
  <div class="chat-container">
    <div class="chat-header">
      <div class="header-content">
        <div class="title-area">
          <h1 class="text-xl font-bold text-indigo-600">EMQX Knowledge Base</h1>
          <p class="text-sm text-gray-500 mt-1">
            Ask questions or analyze logs with our AI assistant
          </p>
        </div>

        <!-- User info in header -->
        <div v-if="user" class="user-area">
          <div class="flex items-center">
            <img
              v-if="user.avatar_url"
              class="h-7 w-7 rounded-full mr-2"
              :src="user.avatar_url"
              alt="User avatar"
            />
            <span class="text-sm text-gray-700 mr-2">{{
              user.name || user.username
            }}</span>
            <button
              @click="logout"
              class="text-sm text-gray-500 hover:text-gray-700 hover:underline"
            >
              Logout
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Chat messages area - always visible, auto-scrolls -->
    <div ref="messagesContainer" class="chat-messages">
      <template v-if="messages.length === 0">
        <div class="empty-state">
          <p>Ask a question, enter EMQX logs, or upload a file to begin</p>
        </div>
      </template>

      <template v-for="(message, index) in messages" :key="index">
        <div
          :class="[
            'message',
            message.role === 'user' ? 'user-message' : 'assistant-message',
          ]"
        >
          <div v-if="message.role === 'user'" class="message-sender">You:</div>
          <div v-else class="message-sender">Assistant:</div>
          <div
            v-if="message.content"
            v-html="renderMarkdown(message.content)"
            class="message-content"
          ></div>
        </div>
      </template>

      <div v-if="isStreaming" class="typing-indicator">
        Assistant is typing...
      </div>
    </div>

    <!-- Status area -->
    <div v-if="error || connectionStatus" class="chat-status">
      <div v-if="error" class="error-message">
        {{ error }}
      </div>
      <div v-if="connectionStatus" class="status-message">
        {{ connectionStatus }}
      </div>
    </div>

    <!-- Input area - fixed at bottom -->
    <div class="chat-input">
      <textarea
        v-model="userInput"
        rows="3"
        class="input-textarea"
        placeholder="Ask a question, paste logs, and optionally include EMQX credentials (endpoint: http://host:18083, username: admin, password: public)"
        :disabled="isLoading || isStreaming"
        @keydown.enter="
          (e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              submitMessage();
            }
          }
        "
      ></textarea>
      <div class="input-help">
        Press Enter to submit, Shift+Enter for a new line
      </div>

      <div class="input-actions">
        <button
          @click="submitMessage"
          :disabled="!canSubmit"
          class="send-button"
        >
          <span v-if="isLoading || isStreaming" class="loading-indicator">
            <svg
              class="spinner"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                class="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                stroke-width="4"
              ></circle>
              <path
                class="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              ></path>
            </svg>
            Processing...
          </span>
          <span v-else>Send</span>
        </button>

        <div class="upload-container">
          <input
            type="file"
            ref="fileInput"
            @change="handleFileUpload"
            class="file-input"
            :disabled="isLoading || isStreaming"
          />
          <button
            type="button"
            class="upload-button"
            :disabled="isLoading || isStreaming"
            @click="fileInput?.click()"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="upload-icon"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
              />
            </svg>
            Upload
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import {
  ref,
  computed,
  onBeforeUnmount,
  onMounted,
  watch,
  nextTick,
  inject,
} from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";

// Get user info and logout function from parent
const user = inject("user");
const logout = inject("logout");

// State variables
const userInput = ref("");
const messages = ref([]);
const isLoading = ref(false);
const isStreaming = ref(false);
const error = ref("");
const fileInput = ref(null);
const connectionStatus = ref("");
const messagesContainer = ref(null);
let wsConnection = null;
let sessionId = null;

// Initialize a variable to track last scroll time
let lastScrollTime = 0;

// Computed properties
const canSubmit = computed(() => {
  return userInput.value.trim() && !isLoading.value && !isStreaming.value;
});

// Format file size
const formatFileSize = (bytes) => {
  if (bytes < 1024) return bytes + " bytes";
  else if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  else return (bytes / (1024 * 1024)).toFixed(1) + " MB";
};

// Render markdown
const renderMarkdown = (text) => {
  if (!text) return "";
  const html = marked.parse(text);
  return DOMPurify.sanitize(html);
};

// Auto-scroll when messages update
watch(messages, () => {
  scrollToBottom(true);
});

// Also scroll when streaming status changes
watch(isStreaming, (newValue) => {
  if (!newValue) {
    // When streaming ends, scroll to bottom
    scrollToBottom(true);
  }
});

// Function to scroll to bottom of messages with throttling
const scrollToBottom = (force = true) => {
  const now = Date.now();

  // If forced or it's been at least 300ms since last scroll, scroll now
  if (force || now - lastScrollTime > 300) {
    lastScrollTime = now;

    nextTick(() => {
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop =
          messagesContainer.value.scrollHeight;
      }
    });
  }
};

// Handle file upload
const handleFileUpload = async (event) => {
  const file = event.target.files[0];
  if (file) {
    // Show loading indicator
    isLoading.value = true;
    error.value = "";

    try {
      // Read file content
      const fileContent = await readFile(file);

      // Set the file name as the user input to show what's being analyzed
      userInput.value = `Analyzing file: ${file.name}`;

      // Store the file for later submission
      localStorage.setItem(
        "pendingFileObject",
        JSON.stringify({
          name: file.name,
          size: file.size,
          type: file.type,
          lastModified: file.lastModified,
        }),
      );

      // Update UI to indicate file is ready to be sent
      connectionStatus.value = `File "${file.name}" loaded and ready to send`;

      // No auto-submission - user must click send button
    } catch (err) {
      console.error("Error processing file:", err);
      error.value = "Failed to read the file. Please try another file.";
    } finally {
      // Reset loading state
      isLoading.value = false;

      // Reset the file input so the same file can be selected again
      if (fileInput.value) {
        fileInput.value.value = "";
      }
    }
  }
};

// Read file content
const readFile = (file) => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = (e) => {
      try {
        // Store the file content
        const fileContent = e.target.result;
        if (!fileContent || fileContent.length === 0) {
          console.error("File read returned empty content");
          reject(new Error("File appears to be empty"));
          return;
        }

        // Store in localStorage
        localStorage.setItem("lastInputContent", fileContent);
        console.log("File content stored successfully:", {
          fileName: file.name,
          fileSize: file.size,
          contentLength: fileContent.length,
        });

        resolve(fileContent);
      } catch (err) {
        console.error("Error in file reader onload:", err);
        reject(err);
      }
    };

    reader.onerror = (error) => {
      console.error("FileReader error:", error);
      reject(new Error("Failed to read the file"));
    };

    reader.readAsText(file);
  });
};

// Submit the user's message
const submitMessage = async (fileObj = null) => {
  // Check for pending file
  const pendingFileJson = localStorage.getItem("pendingFileObject");
  let hasPendingFile = false;

  if (pendingFileJson) {
    hasPendingFile = true;
    fileObj = { isStoredFile: true };
    localStorage.removeItem("pendingFileObject"); // Clear after using
  }

  if (!userInput.value.trim() && !hasPendingFile && !fileObj) return;

  // Store the input before clearing it
  const inputText = userInput.value.trim();
  userInput.value = "";

  // Add the message to the chat history
  messages.value.push({
    role: "user",
    content: inputText,
  });

  // Scroll to show the user's message
  scrollToBottom(true);

  // Store the input content (could be a question or logs)
  if (!hasPendingFile) {
    localStorage.setItem("lastInputContent", inputText);
  }

  // Clear the file loaded status
  if (
    connectionStatus.value &&
    connectionStatus.value.includes("loaded and ready")
  ) {
    connectionStatus.value = "";
  }

  // Send the message
  try {
    await sendMessage(fileObj);
  } catch (error) {
    console.error("Error submitting message:", error);
  }
};

// Send message to WebSocket
const sendMessage = async (fileObj = null) => {
  try {
    // Reset error state
    error.value = "";

    // If we're already processing, don't submit again
    if (isStreaming.value) {
      console.log("Already streaming, not sending another message");
      return;
    }

    // Create a placeholder for the assistant's response
    messages.value.push({
      role: "assistant",
      content: "",
    });

    // Start streaming
    isStreaming.value = true;

    // Ensure WebSocket connection
    await ensureWebSocketConnection();

    // Determine if this is the first message
    const isFirstMessage =
      messages.value.filter((m) => m.role === "assistant").length <= 1;

    // Prepare the message payload
    const payload = {};

    // Get the user's input
    const userMessages = messages.value.filter((m) => m.role === "user");
    const lastUserMessage = userMessages[userMessages.length - 1].content;

    // For any message, we include the content as a message
    payload.message = lastUserMessage;

    // If we have a file, we treat it as a special case
    if (fileObj) {
      const fileContent = localStorage.getItem("lastInputContent");
      if (fileContent) {
        payload.content = fileContent;

        // Add a debug message
        console.log("File content detected and included in payload:", {
          contentLength: fileContent.length,
          fileName:
            fileObj.name || (fileObj.isStoredFile ? "stored file" : "unknown"),
          messageText: lastUserMessage,
        });
      } else {
        console.error("No file content found in localStorage");
      }
    } else if (isFirstMessage) {
      // If it's the first message and not a file, include the content as is
      // The backend will determine if it's a log or a question
      payload.content = lastUserMessage;
    }

    // Log the payload for debugging
    console.log("Sending payload:", {
      messageCount: messages.value.length,
      isFirstMessage: isFirstMessage,
      hasContent: !!payload.content,
      contentType: fileObj ? "file" : "text",
      contentLength: payload.content ? payload.content.length : 0,
      message: payload.message,
    });

    // Send the message
    wsConnection.send(JSON.stringify(payload));

    // Return a promise that resolves when the streaming is complete
    return new Promise((resolve) => {
      const checkInterval = setInterval(() => {
        if (!isStreaming.value) {
          clearInterval(checkInterval);
          resolve();
        }
      }, 100);

      // Set a timeout to prevent hanging
      setTimeout(() => {
        clearInterval(checkInterval);
        if (isStreaming.value) {
          isStreaming.value = false;
          error.value = "Request timed out. Please try again.";
        }
        resolve();
      }, 120000); // 2 minute timeout
    });
  } catch (err) {
    console.error("Error sending message:", err);
    error.value = "Failed to send message. Please try again.";
    isStreaming.value = false;
    throw err;
  }
};

// Ensure WebSocket connection
const ensureWebSocketConnection = () => {
  return new Promise((resolve, reject) => {
    // If we already have a connection, use it
    if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
      resolve();
      return;
    }

    // Close any existing connection
    if (wsConnection) {
      wsConnection.close();
      wsConnection = null;
    }

    // Determine WebSocket URL
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    // Add token as query parameter for authentication
    const token = localStorage.getItem("auth_token") || "LOCAL_DEV_TOKEN";
    const wsUrl = `${protocol}//${window.location.host}/ws/chat?token=${encodeURIComponent(token)}`;

    connectionStatus.value = "Connecting to WebSocket...";
    console.log(`Connecting to WebSocket at ${wsUrl}`);

    // Create a new WebSocket connection
    wsConnection = new WebSocket(wsUrl);

    // Set up event handlers
    wsConnection.onopen = () => {
      connectionStatus.value = "WebSocket connected";
      console.log("WebSocket connection established");

      // Start ping interval to keep the connection alive
      startPingInterval();

      resolve();
    };

    wsConnection.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log("Received WebSocket message:", data.type);

        // Handle different message types
        if (data.type === "error") {
          console.error("WebSocket error:", data.data);
          error.value = data.data;
          isStreaming.value = false;

          // Handle specific error cases
          if (data.data && data.data.includes("No active session found")) {
            // Session expired, let's try to recover
            const currentMessage = messages.value[messages.value.length - 1];

            // Add an error notice to the current assistant message
            if (currentMessage && currentMessage.role === "assistant") {
              currentMessage.content +=
                "\n\n*Session expired. Attempting to restart...*";
            }

            // Scroll to show the error message
            scrollToBottom(true);

            // Get the stored content
            const storedContent = localStorage.getItem("lastInputContent");
            if (storedContent) {
              // Automatically restart with the same content
              setTimeout(() => {
                console.log("Restarting with stored content...");
                const payload = {
                  content: storedContent,
                  message: userInput.value, // Include current input as a specific question
                };

                // Clear current input and inform the user
                userInput.value = "";

                // Send the new request
                wsConnection.send(JSON.stringify(payload));
              }, 1000);
            } else {
              // No content available, can't auto-recover
              if (currentMessage && currentMessage.role === "assistant") {
                currentMessage.content +=
                  "\n\nUnable to recover session. Please try again.";
                scrollToBottom(true);
              }
            }
          }
        } else if (data.type === "clear") {
          // Clear the current assistant message to prevent duplicate content
          if (isStreaming.value && messages.value.length > 0) {
            const currentMessage = messages.value[messages.value.length - 1];
            if (currentMessage.role === "assistant") {
              // Clear existing content to prepare for the new analysis
              currentMessage.content = "";
              console.log("Cleared assistant message content for new response");

              // Add a temporary message to indicate processing
              if (data.data === "log_analysis") {
                currentMessage.content = "*Analyzing logs...*\n\n";
                console.log("Preparing for log analysis");
              } else {
                currentMessage.content = "*Generating response...*\n\n";
                console.log("Preparing for general response");
              }
              scrollToBottom(true);
            }
          }
        } else if (data.type === "done" || data.type === "message_complete") {
          console.log("Response complete");
          connectionStatus.value = "";
          isStreaming.value = false;
          scrollToBottom(true);
        } else if (data.type === "pong") {
          console.log("WebSocket heartbeat received");
        } else if (data.type === "token") {
          // Stream tokens to the current assistant message
          if (isStreaming.value && messages.value.length > 0) {
            const currentMessage = messages.value[messages.value.length - 1];
            if (currentMessage.role === "assistant") {
              // If we see the start of a final report, clear the temporary message
              if (
                (data.data.includes("# EMQX Log Analysis") ||
                  data.data.includes("EMQX Log Analysis")) &&
                currentMessage.content === "*Generating response...*\n\n"
              ) {
                currentMessage.content = "";
              }

              // Append the token
              currentMessage.content += data.data;

              // Smart scrolling based on content
              if (data.data.includes("\n")) {
                scrollToBottom(true);
              } else {
                // Regular token, use throttled scrolling
                scrollToBottom(false);
              }
            }
          }
        } else if (data.type === "message") {
          // Append full message to the current assistant message
          if (isStreaming.value && messages.value.length > 0) {
            const currentMessage = messages.value[messages.value.length - 1];
            if (currentMessage.role === "assistant") {
              // If content exists but doesn't end with period, question mark, or exclamation, add one
              if (
                currentMessage.content &&
                !currentMessage.content.endsWith(".") &&
                !currentMessage.content.endsWith("?") &&
                !currentMessage.content.endsWith("!") &&
                !currentMessage.content.endsWith("*\n\n")
              ) {
                currentMessage.content += ". ";
              }
              // If current content doesn't end with proper spacing, add it
              else if (
                currentMessage.content &&
                !currentMessage.content.endsWith("\n\n")
              ) {
                currentMessage.content += "\n\n";
              }
              currentMessage.content += data.data;
              scrollToBottom(true);
            }
          }
        } else if (data.type === "input_required") {
          // For input required, add it to the assistant's message and wait for user input
          if (messages.value.length > 0) {
            const currentMessage = messages.value[messages.value.length - 1];
            if (currentMessage.role === "assistant") {
              // Add spacing before the input request
              if (
                currentMessage.content &&
                !currentMessage.content.endsWith("\n\n")
              ) {
                currentMessage.content += "\n\n";
              }
              currentMessage.content += data.data;
              isStreaming.value = false;
              scrollToBottom(true);
            }
          }
        } else if (data.type === "markdown_response") {
          // Handle markdown analysis response
          console.log(
            "Received markdown analysis response, length:",
            data.data.length,
          );

          if (messages.value.length > 0) {
            const currentMessage = messages.value[messages.value.length - 1];
            if (currentMessage.role === "assistant") {
              // Replace the temporary content with the full markdown
              currentMessage.content = data.data;
              console.log("Updated message content with markdown response");
              scrollToBottom(true);
            }
          }
        } else if (data.type === "status") {
          // Update status display without affecting message content
          connectionStatus.value = data.data;
          console.log("Status updated:", data.data);
        } else if (data.type === "broker_info") {
          // Handle all broker information
          console.log("Received broker_info event");

          if (data.data) {
            console.log("Adding broker info to chat");
            // Add broker info as a separate assistant message
            messages.value.push({
              role: "assistant",
              content: data.data,
              timestamp: new Date().toISOString(),
            });
            scrollToBottom(true);
          }
        } else {
          // Legacy support - append content to the current message
          if (isStreaming.value && messages.value.length > 0) {
            const currentMessage = messages.value[messages.value.length - 1];
            if (currentMessage.role === "assistant") {
              currentMessage.content += data.message || "";
              scrollToBottom(true);
            }
          }
        }
      } catch (error) {
        console.error("Error parsing WebSocket message:", error);
      }
    };

    wsConnection.onerror = (err) => {
      console.error("WebSocket error:", err);
      error.value = "WebSocket connection error";
      isStreaming.value = false;
      reject(err);
    };

    wsConnection.onclose = (event) => {
      console.log("WebSocket closed:", event.code, event.reason);
      connectionStatus.value = `WebSocket closed: ${event.code}`;
      isStreaming.value = false;

      // Clear ping interval
      clearPingInterval();

      // If this was an abnormal closure, reject the promise
      if (event.code !== 1000 && event.code !== 1001) {
        reject(new Error(`WebSocket closed: ${event.code}`));
      }
    };

    // Set a timeout for the connection
    setTimeout(() => {
      if (wsConnection.readyState !== WebSocket.OPEN) {
        wsConnection.close();
        connectionStatus.value = "Connection timed out";
        reject(new Error("WebSocket connection timed out"));
      }
    }, 10000); // 10 second timeout
  });
};

// Ping interval to keep the connection alive
let pingIntervalId = null;

const startPingInterval = () => {
  // Clear any existing interval
  clearPingInterval();

  // Set up a new interval to ping the server every 30 seconds
  pingIntervalId = setInterval(() => {
    if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
      console.log("Sending ping to server");
      wsConnection.send(JSON.stringify({ ping: true }));
    } else {
      clearPingInterval();
    }
  }, 30000); // 30 seconds
};

const clearPingInterval = () => {
  if (pingIntervalId) {
    clearInterval(pingIntervalId);
    pingIntervalId = null;
  }
};

// Set initial connection status
onMounted(() => {
  connectionStatus.value = "Ready to assist";

  // Initial scroll to bottom
  scrollToBottom(true);

  // Initialize periodically refreshing sessions if there's an active analysis
  startSessionRefresh();
});

onBeforeUnmount(() => {
  // Clean up WebSocket connection
  if (wsConnection) {
    wsConnection.close();
  }

  // Stop the session refresh interval
  stopSessionRefresh();
});

// Session refresh mechanism
let sessionRefreshInterval = null;

// Start refreshing the session periodically
const startSessionRefresh = () => {
  // Stop any existing refresh interval
  stopSessionRefresh();

  // Create a new refresh interval that sends a ping every 10 minutes
  sessionRefreshInterval = setInterval(
    () => {
      // Only refresh if we have an active session (check if we have messages)
      if (messages.value.length > 0) {
        refreshSession();
      }
    },
    10 * 60 * 1000,
  ); // 10 minutes
};

// Stop the session refresh interval
const stopSessionRefresh = () => {
  if (sessionRefreshInterval) {
    clearInterval(sessionRefreshInterval);
    sessionRefreshInterval = null;
  }
};

// Refresh the session by sending a ping to the server
const refreshSession = async () => {
  try {
    // Ensure WebSocket connection
    await ensureWebSocketConnection();

    // Send a ping to keep the connection alive
    const payload = { ping: true };
    wsConnection.send(JSON.stringify(payload));

    // Log the refresh attempt
    console.log("Session refresh ping sent");
  } catch (err) {
    console.error("Error refreshing session:", err);
  }
};

// Modal functions have been removed since credentials are now included in the initial message
</script>

<style scoped>
.chat-container {
  display: flex;
  flex-direction: column;
  height: 90vh;
  width: 100%;
  background-color: white;
  border-radius: 0.375rem;
  box-shadow:
    0 1px 3px 0 rgba(0, 0, 0, 0.1),
    0 1px 2px 0 rgba(0, 0, 0, 0.06);
  margin: 0;
}

.chat-header {
  padding: 0.75rem 1rem;
  background-color: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title-area {
  flex: 1;
}

.user-area {
  text-align: right;
  min-width: 160px;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  min-height: 100px;
}

.chat-status {
  padding: 0.5rem 1rem;
  background-color: #f9fafb;
  border-top: 1px solid #e5e7eb;
  border-bottom: 1px solid #e5e7eb;
}

.user-info {
  padding: 0.25rem 1rem;
  background-color: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
  font-size: 0.875rem;
}

.chat-input {
  padding: 0.75rem 1rem;
  background-color: #f9fafb;
  border-top: 1px solid #e5e7eb;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #9ca3af;
}

.message {
  padding: 0.75rem;
  border-radius: 0.375rem;
  margin-bottom: 0.75rem;
}

.user-message {
  background-color: #eff6ff;
  margin-left: 3rem;
}

.assistant-message {
  background-color: #f9fafb;
  margin-right: 3rem;
}

.message-sender {
  font-weight: 500;
  margin-bottom: 0.25rem;
}

.user-message .message-sender {
  color: #1d4ed8;
}

.assistant-message .message-sender {
  color: #374151;
}

.message-content {
  font-size: 0.875rem;
}

.typing-indicator {
  color: #6b7280;
  margin-left: 1rem;
  animation: pulse 1.5s infinite;
}

.error-message {
  color: #dc2626;
  font-size: 0.875rem;
}

.status-message {
  color: #6b7280;
  font-size: 0.75rem;
}

.input-textarea {
  width: 100%;
  border-radius: 0.375rem;
  border: 1px solid #d1d5db;
  padding: 0.75rem;
  font-size: 0.875rem;
  resize: none;
}

.input-textarea:focus {
  outline: none;
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.input-help {
  font-size: 0.75rem;
  color: #6b7280;
  margin-top: 0.25rem;
}

.input-actions {
  display: flex;
  margin-top: 0.75rem;
  gap: 1rem;
}

.send-button {
  display: inline-flex;
  align-items: center;
  padding: 0.5rem 1rem;
  background-color: #4f46e5;
  color: white;
  border: none;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
}

.send-button:hover {
  background-color: #4338ca;
}

.send-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-indicator {
  display: flex;
  align-items: center;
}

.spinner {
  animation: spin 1s linear infinite;
  width: 1rem;
  height: 1rem;
  margin-right: 0.5rem;
}

.upload-container {
  position: relative;
}

.file-input {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}

.upload-button {
  display: inline-flex;
  align-items: center;
  padding: 0.5rem 1rem;
  background-color: white;
  color: #374151;
  border: 1px solid #d1d5db;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
}

.upload-button:hover {
  background-color: #f9fafb;
}

.upload-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.upload-icon {
  width: 1rem;
  height: 1rem;
  margin-right: 0.5rem;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* Markdown styling */
.message-content :deep(code) {
  background-color: #f3f4f6;
  padding: 0.125rem 0.25rem;
  border-radius: 0.25rem;
  font-family: monospace;
  font-size: 0.875em;
}

.message-content :deep(pre) {
  background-color: #f3f4f6;
  padding: 0.75rem;
  border-radius: 0.375rem;
  overflow-x: auto;
  margin-bottom: 0.75rem;
}

.message-content :deep(pre code) {
  background-color: transparent;
  padding: 0;
  border-radius: 0;
}

.message-content :deep(p) {
  margin-bottom: 0.5rem;
}

.message-content :deep(ul),
.message-content :deep(ol) {
  padding-left: 1.5rem;
  margin-bottom: 0.75rem;
}

.message-content :deep(ul) {
  list-style-type: disc;
}

.message-content :deep(ol) {
  list-style-type: decimal;
}
</style>
