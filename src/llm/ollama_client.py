# -*- coding: utf-8 -*-
"""
src/llm/ollama_client.py
Local Ollama client with retries, timeout management, and fallback model options.
"""
import json
import time
import requests
from typing import Dict, Any, Optional
from src.llm.prompts import SYSTEM_PROMPT

def clean_json_response(raw_text: str) -> str:
    """
    Cleans raw model output to ensure it contains only a single JSON object.
    Strips markdown code blocks and trailing explanations if present.
    """
    text = raw_text.strip()
    
    # Strip markdown wrapper if present
    if text.startswith("```"):
        # Match ```json ... ``` or similar
        m = re.match(r"^```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if m:
            text = m.group(1).strip()
            
    # Find first '{' and last '}'
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace:last_brace + 1]
        
    return text

# Compile re inside the script since we need it in clean_json_response
import re

class OllamaClient:
    """
    Ollama API wrapper for text generation.
    """
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        primary_model: str = "qwen3:14b",
        fallback_model: str = "llama3",
        timeout: int = 15,
        max_retries: int = 3,
        backoff_factor: float = 1.5
    ):
        self.base_url = base_url.rstrip("/")
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.active_model = self.primary_model

    def check_model_availability(self, model: str) -> bool:
        """
        Queries Ollama tags list to check if model is loaded.
        """
        url = f"{self.base_url}/api/tags"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                models_list = response.json().get("models", [])
                for m in models_list:
                    if m.get("name") == model or m.get("name").split(":")[0] == model.split(":")[0]:
                        return True
        except requests.RequestException:
            pass
        return False

    def query_embeddings(self, text: str, model: str) -> Optional[list]:
        """
        Calls Ollama embeddings endpoint.
        """
        url = f"{self.base_url}/api/embeddings"
        payload = {"model": model, "prompt": text}
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            if response.status_code == 200:
                return response.json().get("embedding")
        except requests.RequestException:
            pass
        return None

    def generate_chat(self, user_prompt: str) -> Optional[str]:
        """
        Sends system and user messages to the active model using Ollama's chat API.
        """
        # Resolve active model on first call
        if self.active_model == self.primary_model:
            if not self.check_model_availability(self.primary_model):
                print(f"[Ollama Client] Primary model '{self.primary_model}' not found. Falling back to '{self.fallback_model}'.")
                self.active_model = self.fallback_model

        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.active_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0
            }
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(url, json=payload, timeout=self.timeout)
                if response.status_code == 200:
                    result = response.json()
                    return result.get("message", {}).get("content", "").strip()
            except requests.RequestException as e:
                if attempt == self.max_retries:
                    print(f"[Ollama Client] Error: Chat generation failed after {self.max_retries} attempts ({e})")
                    return None
                time.sleep(self.backoff_factor ** attempt)
        return None
