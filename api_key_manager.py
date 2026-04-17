import os
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import random

logger = logging.getLogger(__name__)

class APIKeyManager:
    """مدير المفاتيح المتعددة مع التبديل التلقائي"""
    
    def __init__(self):
        self.keys: Dict[str, List[Dict]] = {
            'deepseek': [],
            'openrouter': [],
            'groq': [],
            'gemini': [],
            'openai': []
        }
        self.key_status: Dict[str, Dict[str, any]] = {}  # tracking usage
        self.current_keys: Dict[str, int] = {}  # current index for each service
        self.load_keys_from_env()
    
    def load_keys_from_env(self):
        """تحميل المفاتيح من متغيرات البيئة"""
        
        # DeepSeek keys (9 مفاتيح)
        for i in range(1, 10):
            key = os.environ.get(f"DEEPSEEK_API_KEY_{i}")
            if key:
                self.add_key('deepseek', key, f'deepseek_{i}')
        
        # OpenRouter keys (9 مفاتيح)
        for i in range(1, 10):
            key = os.environ.get(f"OPENROUTER_API_KEY_{i}")
            if key:
                self.add_key('openrouter', key, f'openrouter_{i}')
        
        # Groq keys (9 مفاتيح)
        for i in range(1, 10):
            key = os.environ.get(f"GROQ_API_KEY_{i}")
            if key:
                self.add_key('groq', key, f'groq_{i}')
        
        # Gemini keys (9 مفاتيح)
        for i in range(1, 10):
            key = os.environ.get(f"GEMINI_API_KEY_{i}")
            if key:
                self.add_key('gemini', key, f'gemini_{i}')
        
        # OpenAI keys (9 مفاتيح)
        for i in range(1, 10):
            key = os.environ.get(f"OPENAI_API_KEY_{i}")
            if key:
                self.add_key('openai', key, f'openai_{i}')
        
        # أيضاً دعم المفاتيح الفردية (للخلف)
        if os.environ.get("DEEPSEEK_API_KEY") and not self.keys['deepseek']:
            self.add_key('deepseek', os.environ.get("DEEPSEEK_API_KEY"), 'deepseek_main')
        if os.environ.get("OPENROUTER_API_KEY") and not self.keys['openrouter']:
            self.add_key('openrouter', os.environ.get("OPENROUTER_API_KEY"), 'openrouter_main')
        if os.environ.get("GROQ_API_KEY") and not self.keys['groq']:
            self.add_key('groq', os.environ.get("GROQ_API_KEY"), 'groq_main')
        if os.environ.get("GEMINI_API_KEY") and not self.keys['gemini']:
            self.add_key('gemini', os.environ.get("GEMINI_API_KEY"), 'gemini_main')
        if os.environ.get("OPENAI_API_KEY") and not self.keys['openai']:
            self.add_key('openai', os.environ.get("OPENAI_API_KEY"), 'openai_main')
        
        # إحصائيات التحميل
        for service, keys in self.keys.items():
            logger.info(f"Loaded {len(keys)} keys for {service}")
    
    def add_key(self, service: str, api_key: str, key_id: str):
        """إضافة مفتاح جديد"""
        self.keys[service].append({
            'key': api_key,
            'id': key_id,
            'usage_count': 0,
            'error_count': 0,
            'last_error': None,
            'last_used': None,
            'is_active': True
        })
        self.current_keys[service] = 0
    
    def get_next_key(self, service: str) -> Optional[Tuple[str, str]]:
        """الحصول على المفتاح التالي المتاح"""
        if service not in self.keys or not self.keys[service]:
            return None
        
        keys_list = self.keys[service]
        start_index = self.current_keys.get(service, 0)
        
        # جرب كل المفاتيح بدءاً من المؤشر الحالي
        for i in range(len(keys_list)):
            idx = (start_index + i) % len(keys_list)
            key_info = keys_list[idx]
            
            if key_info['is_active']:
                # تحديث المؤشر الحالي
                self.current_keys[service] = (idx + 1) % len(keys_list)
                key_info['last_used'] = datetime.now()
                key_info['usage_count'] += 1
                
                logger.info(f"Using {service} key: {key_info['id']} (usage: {key_info['usage_count']})")
                return key_info['key'], key_info['id']
        
        return None
    
    def mark_key_error(self, service: str, key_id: str, error_msg: str = ""):
        """تسجيل خطأ في مفتاح معين"""
        for key_info in self.keys.get(service, []):
            if key_info['id'] == key_id:
                key_info['error_count'] += 1
                key_info['last_error'] = error_msg
                
                # إذا تكرر الخطأ 3 مرات، فعّل المفتاح
                if key_info['error_count'] >= 3:
                    key_info['is_active'] = False
                    logger.warning(f"Deactivating {service} key: {key_id} after 3 errors")
                else:
                    logger.warning(f"Error on {service} key: {key_id} (attempt {key_info['error_count']}/3): {error_msg[:100]}")
                break
    
    def mark_key_success(self, service: str, key_id: str):
        """تسجيل نجاح للمفتاح"""
        for key_info in self.keys.get(service, []):
            if key_info['id'] == key_id:
                key_info['error_count'] = 0
                key_info['last_error'] = None
                key_info['is_active'] = True
                break
    
    def get_stats(self) -> Dict:
        """الحصول على إحصائيات جميع المفاتيح"""
        stats = {}
        for service, keys in self.keys.items():
            stats[service] = {
                'total': len(keys),
                'active': sum(1 for k in keys if k['is_active']),
                'total_usage': sum(k['usage_count'] for k in keys),
                'keys': [
                    {
                        'id': k['id'],
                        'usage': k['usage_count'],
                        'errors': k['error_count'],
                        'active': k['is_active']
                    }
                    for k in keys
                ]
            }
        return stats
    
    def get_any_available_service(self) -> Optional[str]:
        """الحصول على أي خدمة متاحة"""
        services_order = ['groq', 'gemini', 'deepseek', 'openrouter', 'openai']
        for service in services_order:
            if self.keys[service] and any(k['is_active'] for k in self.keys[service]):
                return service
        return None


# إنشاء مدير عام
key_manager = APIKeyManager()
