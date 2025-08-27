"""
Analytics tracking for flight data requests and responses
"""

import os
import logging
from typing import Dict, Any, Optional, List
from mixpanel import Mixpanel
import time

logger = logging.getLogger(__name__)

class Analytics:
    """Analytics wrapper for Mixpanel tracking"""
    
    def __init__(self):
        self.mixpanel_token = os.environ.get('MIXPANEL_TOKEN')
        self.mp = None
        
        if self.mixpanel_token:
            try:
                self.mp = Mixpanel(self.mixpanel_token)
                logger.info("Mixpanel analytics initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Mixpanel: {e}")
                self.mp = None
        else:
            logger.info("MIXPANEL_TOKEN not set, analytics disabled")
    
    def track_event(self, event_name: str, properties: Dict[str, Any], user_id: Optional[str] = None):
        """Track an event with properties"""
        if not self.mp:
            return
            
        try:
            # Add timestamp and basic properties
            properties.update({
                'timestamp': int(time.time()),
                'app_version': '0.1.0'
            })
            
            if user_id:
                self.mp.track(user_id, event_name, properties)
            else:
                # Use anonymous tracking
                self.mp.track('anonymous', event_name, properties)
                
        except Exception as e:
            logger.error(f"Failed to track event {event_name}: {e}")
    

# Global analytics instance
analytics = Analytics()