import os
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class APIKeyManager:
    """مدير المفاتيح المتعددة - يدعم المفاتيح المفصولة بفواصل"""
    
    def __init__(self):
        self.keys: Dict[str, List[Dict]] = {
            'openai': [],
            'gemini': [],
            'groq': [],
            'deepseek': [],
            'openrouter': []
        }
        self.current_keys: Dict[str, int] = {}
        self.load_keys_from_env()
    
    def load_keys_from_env(self):
        """تحميل المفاتيح من متغيرات البيئة (تدعم الفواصل)"""
        
        # قائمة المتغيرات التي قد تحتوي على مفاتيح متعددة مفصولة بفواصل
        key_vars = {
            'openai': ['OPENAI_API_KEYS', 'OPENAI_API_KEY'],
            'gemini': ['GEMINI_API_KEYS', 'GEMINI_API_KEY'],
            'groq': ['GROQ_API_KEYS', 'GROQ_API_KEY'],
            'deepseek': ['DEEPSEEK_API_KEYS', 'DEEPSEEK_API_KEY'],
            'openrouter': ['OPENROUTER_API_KEYS', 'OPENROUTER_API_KEY']
        }
        
        for service, var_names in key_vars.items():
            all_keys = []
            
            for var_name in var_names:
                value = os.environ.get(var_name, "")
                if value:
                    # تقسيم النص على الفواصل
                    parts = value.split(',')
                    for part in parts:
                        key = part.strip()
                        if key and len(key) > 10:  # التأكد أن المفتاح صالح
                            all_keys.append(key)
            
            # إضافة المفاتيح إلى القائمة
            for idx, key in enumerate(all_keys):
                self.add_key(service, key, f"{service}_{idx+1}")
            
            logger.info(f"Loaded {len(all_keys)} keys for {service}")
    
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
        if service not in self.current_keys:
            self.current_keys[service] = 0
    
    def get_next_key(self, service: str) -> Optional[Tuple[str, str]]:
        """الحصول على المفتاح التالي المتاح"""
        if service not in self.keys or not self.keys[service]:
            return None
        
        keys_list = self.keys[service]
        start_index = self.current_keys.get(service, 0)
        
        for i in range(len(keys_list)):
            idx = (start_index + i) % len(keys_list)
            key_info = keys_list[idx]
            
            if key_info['is_active']:
                self.current_keys[service] = (idx + 1) % len(keys_list)
                key_info['last_used'] = datetime.now()
                key_info['usage_count'] += 1
                logger.info(f"Using {service} key: {key_info['id']}")
                return key_info['key'], key_info['id']
        
        return None
    
    def mark_key_error(self, service: str, key_id: str, error_msg: str = ""):
        """تسجيل خطأ في مفتاح معين"""
        for key_info in self.keys.get(service, []):
            if key_info['id'] == key_id:
                key_info['error_count'] += 1
                key_info['last_error'] = error_msg
                
                if key_info['error_count'] >= 3:
                    key_info['is_active'] = False
                    logger.warning(f"Deactivating {service} key: {key_id}")
                break
    
    def mark_key_success(self, service: str, key_id: str):
        """تسجيل نجاح للمفتاح"""
        for key_info in self.keys.get(service, []):
            if key_info['id'] == key_id:
                key_info['error_count'] = 0
                key_info['is_active'] = True
                break
    
    def get_stats(self) -> Dict:
        """الحصول على إحصائيات"""
        stats = {}
        for service, keys in self.keys.items():
            stats[service] = {
                'total': len(keys),
                'active': sum(1 for k in keys if k['is_active']),
                'total_usage': sum(k['usage_count'] for k in keys)
            }
        return stats


key_manager = APIKeyManager()
