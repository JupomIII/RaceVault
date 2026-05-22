from __future__ import annotations
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class AthleteManager:
    """Manages athlete profiles and their best times across all parsed PDFs."""
    
    def __init__(self, output_dir: str, athletes_db_path: str):
        """
        Args:
            output_dir: Directory containing parsed JSON results
            athletes_db_path: Path to athlete profiles JSON file
        """
        self.output_dir = output_dir
        self.athletes_db_path = athletes_db_path
        self.athletes: Dict[str, Dict[str, Any]] = {}
        self.load_athletes_db()
    
    def load_athletes_db(self) -> None:
        """Load athlete profiles from JSON file."""
        if os.path.exists(self.athletes_db_path):
            try:
                with open(self.athletes_db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.athletes = {k: v for k, v in data.items()}
            except Exception as e:
                logger.error(f"Failed to load athletes DB: {e}")
                self.athletes = {}
        else:
            self.athletes = {}
    
    def save_athletes_db(self) -> None:
        """Save athlete profiles to JSON file."""
        try:
            Path(self.athletes_db_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.athletes_db_path, 'w', encoding='utf-8') as f:
                json.dump(self.athletes, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save athletes DB: {e}")
    
    def rebuild_from_outputs(self) -> None:
        """Scan all output JSONs and rebuild athlete profiles with best times."""
        athletes_dict: Dict[str, Dict[str, Any]] = {}
        
        output_path = Path(self.output_dir)
        if not output_path.exists():
            self.athletes = {}
            return
        
        # Scan all JSON files in output directory
        for json_file in sorted(output_path.glob("*.json")):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to read {json_file}: {e}")
                continue
            
            source_file = data.get("source_file", "")
            
            # Process all events and results
            for event in data.get("events", []):
                event_name = event.get("event_name", "")
                distance = self._extract_distance(event_name)
                boat_class = self._extract_boat_class(event_name)
                
                for result in event.get("results", []):
                    athlete_info = result.get("athlete", {})
                    athlete_name = athlete_info.get("normalized_name") or athlete_info.get("raw_name", "")
                    
                    if not athlete_name:
                        continue
                    
                    time_str = result.get("time", "")
                    if not time_str:
                        continue
                    
                    # Normalize athlete name
                    normalized_name = athlete_name.strip()
                    
                    # Initialize athlete if not exists
                    if normalized_name not in athletes_dict:
                        athletes_dict[normalized_name] = {
                            "name": normalized_name,
                            "birth_date": None,  # Can be added manually
                            "age": None,
                            "best_times": {}  # {distance_boat_key: {time, date, source_file, category}}
                        }
                    
                    # Preserve existing birth_date if present
                    if self.athletes.get(normalized_name, {}).get("birth_date"):
                        athletes_dict[normalized_name]["birth_date"] = self.athletes[normalized_name]["birth_date"]
                    
                    # Create key for best times (distance_boat or just distance for team)
                    is_team = "+" in boat_class or len(boat_class) == 0  # K2, K4, C2, C4 considered team
                    category = "team" if is_team else "individual"
                    
                    time_key = f"{distance}_{boat_class}_{category}" if boat_class else f"{distance}_{category}"
                    
                    # Convert time string to seconds for comparison
                    time_seconds = self._time_to_seconds(time_str)
                    
                    # Update best time if this is better
                    if time_key not in athletes_dict[normalized_name]["best_times"] or \
                       time_seconds < self._time_to_seconds(
                           athletes_dict[normalized_name]["best_times"][time_key].get("time", "99:99.99")
                       ):
                        athletes_dict[normalized_name]["best_times"][time_key] = {
                            "time": time_str,
                            "distance": distance,
                            "boat_class": boat_class,
                            "category": category,
                            "date": self._extract_date_from_filename(source_file),
                            "source_file": source_file
                        }
        
        self.athletes = athletes_dict
        self.save_athletes_db()
    
    def _extract_distance(self, event_name: str) -> str:
        """Extract distance from event name (e.g., '500m', '1000m')."""
        tokens = event_name.split()
        for token in tokens:
            if token.lower().endswith('m') and any(c.isdigit() for c in token):
                return token
        return ""
    
    def _extract_boat_class(self, event_name: str) -> str:
        """Extract boat class from event name (K1, K2, C1, C2, etc.)."""
        # Search for patterns like K1, K2, K4, C1, C2, C4
        event_upper = event_name.upper()
        for boat in ["K4", "K2", "K1", "C4", "C2", "C1"]:
            if boat in event_upper:
                return boat
        return ""
    
    def _time_to_seconds(self, time_str: str) -> float:
        """Convert time string (MM:SS.MS) to total seconds for comparison."""
        try:
            time_str = time_str.strip()
            if ':' in time_str:
                parts = time_str.split(':')
                minutes = int(parts[0])
                seconds = float(parts[1])
                return minutes * 60 + seconds
            else:
                return float(time_str)
        except Exception:
            return 99999.0  # Large number for invalid times
    
    def _extract_date_from_filename(self, filename: str) -> Optional[str]:
        """Try to extract date from filename (YYYY-MM-DD or similar)."""
        # Try common date patterns
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        return None
    
    def get_all_athletes(self) -> List[Dict[str, Any]]:
        """Get all athletes sorted by name."""
        return sorted(self.athletes.values(), key=lambda x: x.get("name", ""))
    
    def get_athlete(self, name: str) -> Optional[Dict[str, Any]]:
        """Get athlete profile by name."""
        return self.athletes.get(name)
    
    def update_athlete_birth_date(self, name: str, birth_date: Optional[str]) -> bool:
        """
        Update athlete birth date and calculate age.
        
        Args:
            name: Athlete name
            birth_date: Birth date in format YYYY-MM-DD or None
            
        Returns:
            True if successful
        """
        if name not in self.athletes:
            return False
        
        self.athletes[name]["birth_date"] = birth_date
        self.athletes[name]["age"] = self._calculate_age(birth_date)
        self.save_athletes_db()
        return True
    
    def _calculate_age(self, birth_date: Optional[str]) -> Optional[int]:
        """Calculate age from birth date."""
        if not birth_date:
            return None
        
        try:
            birth = datetime.strptime(birth_date, "%Y-%m-%d")
            today = datetime.now()
            age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
            return age
        except Exception:
            return None
    
    def get_athlete_card(self, name: str) -> str:
        """Generate a formatted card for an athlete with all their times."""
        athlete = self.get_athlete(name)
        if not athlete:
            return f"Athlete '{name}' not found"
        
        lines = []
        lines.append(f"{'='*60}")
        lines.append(f"Athlete: {athlete['name']}")
        if athlete.get('birth_date'):
            lines.append(f"Birth Date: {athlete['birth_date']}")
            if athlete.get('age'):
                lines.append(f"Age: {athlete['age']} years old")
        lines.append(f"{'='*60}")
        
        if not athlete.get('best_times'):
            lines.append("No times recorded")
        else:
            # Group by distance and category
            times_by_distance = {}
            for key, time_info in athlete['best_times'].items():
                distance = time_info.get('distance', 'Unknown')
                if distance not in times_by_distance:
                    times_by_distance[distance] = []
                times_by_distance[distance].append(time_info)
            
            for distance in sorted(times_by_distance.keys(), 
                                   key=lambda x: int(x.rstrip('m')) if x.endswith('m') else 0):
                lines.append(f"\n{distance}:")
                for time_info in times_by_distance[distance]:
                    boat = time_info.get('boat_class', 'Solo')
                    category = time_info.get('category', '')
                    time = time_info.get('time', '')
                    date = time_info.get('date', '')
                    lines.append(f"  {boat:5} ({category:10}) - {time:10} ({date})")
        
        lines.append(f"{'='*60}")
        return "\n".join(lines)
