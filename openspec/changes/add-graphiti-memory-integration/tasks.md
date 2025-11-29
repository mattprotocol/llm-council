## 1. Memory Service Module

- [x] 1.1 Create `backend/memory_service.py` with GraphitiMemoryService class
- [x] 1.2 Implement `record_episode()` method for storing messages
- [x] 1.3 Implement `search_memories()` method for retrieving related facts/nodes
- [x] 1.4 Implement `calculate_confidence()` method using configured LLM
- [x] 1.5 Implement `get_memory_response()` for high-confidence memory retrieval
- [x] 1.6 Add async initialization and graceful fallback on Graphiti unavailability

## 2. Configuration Updates

- [x] 2.1 Add `confidence` model configuration to `config.json`
- [x] 2.2 Update `backend/config_loader.py` to load confidence settings
- [x] 2.3 Add memory-related config fields (threshold, max_age_days)
- [x] 2.4 Document configuration options in config.json comments

## 3. Memory Recording Integration

- [x] 3.1 Add user message recording hook in `main.py`
- [x] 3.2 Add council member response recording in `council.py` Stage 1
- [x] 3.3 Add ranking/evaluation recording in `council.py` Stage 2
- [x] 3.4 Add chairman synthesis recording in `council.py` Stage 3
- [x] 3.5 Add direct response recording in `council.py`
- [x] 3.6 Ensure all recording is async/non-blocking

## 4. Memory-Based Response Path

- [x] 4.1 Add memory check before tool/LLM routing in `main.py`
- [x] 4.2 Implement confidence threshold checking
- [x] 4.3 Add memory-based response formatting
- [x] 4.4 Add streaming events for memory retrieval status
- [x] 4.5 Add fallback to normal flow when confidence is low

## 5. Testing

- [x] 5.1 Add test scenario for memory recording
- [x] 5.2 Add test scenario for memory-based response
- [x] 5.3 Add test scenario for confidence threshold
- [x] 5.4 Verify graceful degradation without Graphiti

## 6. Documentation

- [x] 6.1 Update AGENTS.md with memory integration details
- [x] 6.2 Update README.md Key Features section
- [x] 6.3 Update CHANGELOG.md with version entry
