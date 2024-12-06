#!/usr/bin/env python3
import os
import time
import subprocess
import dbus
import tomli
import tomli_w
import shutil
from pathlib import Path
from typing import Dict, Optional, Literal

class MusicPaper:
    def __init__(self):
        self.bus = dbus.SessionBus()
        self.current_wallpaper: Optional[str] = None
        self.backup_config_path = Path("/tmp/hyprpaper.conf.backup")
        self.backup_wallpaper_path = Path("/tmp/swww.wallpaper.backup")
        self.config = self.load_config()
        self.backend = self.config["general"].get("backend", "hyprpaper")
        if self.backend == "hyprpaper":
            self.backup_current_config()
        else:  # swww
            self.backup_current_wallpaper()
        self.using_default_wallpaper = True
        self.last_playback_status = None
        self.expanded_song_wallpapers = self.expand_song_groups()

    def expand_song_groups(self) -> Dict[str, str]:
        expanded_mapping = {}
        song_wallpapers = self.config.get("song_wallpapers", {})

        song_groups = {k[1:]: v for k, v in song_wallpapers.items() if k.startswith('%')}

        for song, wallpaper in song_wallpapers.items():
            if song.startswith('%'): # sry if this is a bad variable to use
                continue

            matched_group = False
            for group_name, group_songs in song_groups.items():
                if isinstance(group_songs, list) and song in group_songs:
                    expanded_mapping[song] = wallpaper
                    matched_group = True
                    break
                elif isinstance(group_songs, str) and song.lower() in group_name.lower():
                    expanded_mapping[song] = group_songs
                    matched_group = True
                    break

            if not matched_group:
                expanded_mapping[song] = wallpaper

        return expanded_mapping

    def load_config(self) -> dict:
        config_dir = Path.home() / ".config" / "musicpaper"
        config_file = config_dir / "config.toml"

        default_config = {
            "general": {
                "wallpaper_dir": str(Path.home() / "Pictures" / "Wallpapers"),
                "check_interval": 5,
                "backend": "hyprpaper",  # or "swww"
                "swww_transition_type": "simple",  # fade, simple, wipe, etc.
                "swww_transition_duration": 3,  # transition duration in seconds
            },
            "song_wallpapers": {
                "track name": "name.jpg",
                "Track name": "name.jpg",
                "Track Name": "name.jpg",
                # Example of song group
                # "%doomer": ["doomer weekend", "gallowdance", "going away"],
                # "%doomer": "doomer.png"
            }
        }

        if not config_file.exists():
            config_dir.mkdir(parents=True, exist_ok=True)
            with open(config_file, "wb") as f:
                tomli_w.dump(default_config, f)
            return default_config

        try:
            with open(config_file, "rb") as f:
                return tomli.load(f)
        except Exception as e:
            print(f"Error loading config file: {e}")
            return default_config

    def backup_current_config(self):
        try:
            hyprpaper_config = Path.home() / ".config" / "hypr" / "hyprpaper.conf"
            if hyprpaper_config.exists():
                shutil.copy2(hyprpaper_config, self.backup_config_path)
                print(f"Backed up current config to {self.backup_config_path}")
        except Exception as e:
            print(f"Error backing up config: {e}")

    def backup_current_wallpaper(self):
        try:
            result = subprocess.run(['swww', 'query'], capture_output=True, text=True, check=True)

            wallpaper_info = result.stdout.strip()
            if 'image: ' in wallpaper_info:
                current_wallpaper = wallpaper_info.split('image: ', 1)[1]

                self.backup_wallpaper_path.write_text(current_wallpaper)
                print(f"Backed up current wallpaper path to {self.backup_wallpaper_path}")

        except subprocess.CalledProcessError:
            # just in case
            try:
                subprocess.run(['swww', 'init'], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error initializing swww: {e}")
        except Exception as e:
            print(f"Error backing up wallpaper: {e}")

    def get_spotify_properties(self):
        try:
            proxy = self.bus.get_object(
                'org.mpris.MediaPlayer2.spotify',
                '/org/mpris/MediaPlayer2'
            )
            properties = dbus.Interface(
                proxy,
                'org.freedesktop.DBus.Properties'
            )
            metadata = properties.Get(
                'org.mpris.MediaPlayer2.Player',
                'Metadata'
            )
            playback_status = properties.Get(
                'org.mpris.MediaPlayer2.Player',
                'PlaybackStatus'
            )
            return metadata, playback_status
        except dbus.exceptions.DBusException:
            return None, None

    def get_song_info(self):
        metadata, playback_status = self.get_spotify_properties()
        if metadata is None:
            self.last_playback_status = None
            return None, None, None

        self.last_playback_status = playback_status
        if playback_status != 'Playing':
            return None, None, playback_status

        try:
            title = str(metadata.get('xesam:title', ''))
            artist = str(metadata.get('xesam:artist', [''])[0])
            return title, artist, playback_status
        except (KeyError, IndexError):
            return None, None, playback_status

    def set_swww_wallpaper(self, filepath: str) -> bool:
        try:
            print(f"Attempting to set wallpaper to: {filepath}")
            transition_type = self.config["general"].get("swww_transition_type", "simple")
            transition_duration = self.config["general"].get("swww_transition_duration", 3)

            subprocess.run(['pgrep', 'swww-daemon'], check=True)
        except subprocess.CalledProcessError:
            try:
                print("swww daemon not running, initializing...")
                subprocess.run(['swww', 'init'], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error initializing swww: {e}")
                return False

        try:
            cmd = [
                'swww', 'img', filepath,
                '--transition-type', transition_type,
                '--transition-duration', str(transition_duration)
            ]
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"swww command output: {result.stdout}")

            time.sleep(0.5)  # Give swww a moment to update kek
            verify_result = subprocess.run(['swww', 'query'], capture_output=True, text=True, check=True)
            current_wallpaper = verify_result.stdout.strip().split(': ', 1)[1] if ': ' in verify_result.stdout else None

            if 'image: ' in current_wallpaper:
                current_wallpaper = current_wallpaper.split('image: ', 1)[1]

            if current_wallpaper == filepath:
                print(f"Successfully verified wallpaper change to: {filepath}")
                return True
            else:
                print(f"Wallpaper verification failed. Current: {current_wallpaper}, Expected: {filepath}")
                return False

        except subprocess.CalledProcessError as e:
            print(f"Error setting swww wallpaper: {e}")
            print(f"Error output: {e.stderr}")
            return False
        except Exception as e:
            print(f"Unexpected error setting wallpaper: {e}")
            return False

    def update_hyprpaper_config(self, filepath: str) -> bool:
        try:
            hyprpaper_config = Path.home() / ".config" / "hypr" / "hyprpaper.conf"
            config_dir = hyprpaper_config.parent
            config_dir.mkdir(parents=True, exist_ok=True)

            if hyprpaper_config.exists():
                config_lines = hyprpaper_config.read_text().splitlines()
            else:
                config_lines = []

            new_config = []
            preload_found = False
            wallpaper_found = False

            for line in config_lines:
                if line.startswith('preload = '):
                    new_config.append(f'preload = {filepath}')
                    preload_found = True
                elif line.startswith('wallpaper = '):
                    new_config.append(f'wallpaper = ,{filepath}')
                    wallpaper_found = True
                else:
                    new_config.append(line)

            if not preload_found:
                new_config.append(f'preload = {filepath}')
            if not wallpaper_found:
                new_config.append(f'wallpaper = ,{filepath}')

            hyprpaper_config.write_text('\n'.join(new_config) + '\n')
            return True
        except Exception as e:
            print(f"Error updating config file: {e}")
            return False

    def restart_hyprpaper(self) -> bool:
        try:
            subprocess.run(['killall', '-e', 'hyprpaper'],
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
            time.sleep(1)
            subprocess.Popen(['hyprpaper'])
            time.sleep(1)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error restarting hyprpaper: {e}")
            return False

    def change_wallpaper(self, wallpaper_name: str) -> bool:
        wallpaper_dir = Path(self.config["general"]["wallpaper_dir"])
        wallpaper_path = str(wallpaper_dir / wallpaper_name)

        if self.current_wallpaper == wallpaper_path:
            return True

        if not os.path.exists(wallpaper_path):
            print(f"Wallpaper not found: {wallpaper_path}")
            return False

        self.current_wallpaper = wallpaper_path

        if self.backend == "hyprpaper":
            return self.update_hyprpaper_config(wallpaper_path) and self.restart_hyprpaper()
        else:  # swww
            return self.set_swww_wallpaper(wallpaper_path)

    def restore_original_config(self) -> bool:
        if self.using_default_wallpaper:
            print("Already using default wallpaper, no need to restore")
            return True

        try:
            if self.backend == "hyprpaper":
                if self.backup_config_path.exists():
                    hyprpaper_config = Path.home() / ".config" / "hypr" / "hyprpaper.conf"
                    shutil.copy2(self.backup_config_path, hyprpaper_config)
                    print("Restored original wallpaper config")
                    success = self.restart_hyprpaper()
                    if success:
                        self.using_default_wallpaper = True
                        self.current_wallpaper = None
                    return success
                return False
            else:  # swww
                if self.backup_wallpaper_path.exists():
                    previous_wallpaper = self.backup_wallpaper_path.read_text().strip()

                    # gets the path so users can do just imagename.png
                    if 'image: ' in previous_wallpaper:
                        previous_wallpaper = previous_wallpaper.split('image: ', 1)[1]

                    print(f"Attempting to restore wallpaper: {previous_wallpaper}")

                    if os.path.exists(previous_wallpaper):
                        success = self.set_swww_wallpaper(previous_wallpaper)
                        if success:
                            print(f"Successfully restored wallpaper to: {previous_wallpaper}")
                            self.using_default_wallpaper = True
                            self.current_wallpaper = None
                            return True
                        else:
                            print("Failed to restore wallpaper")
                            return False
                    else:
                        print(f"Previous wallpaper file not found: {previous_wallpaper}")
                        return False
                else:
                    print("No backup wallpaper path found")
                    return False
        except Exception as e:
            print(f"Error restoring config: {e}")
            return False

    def run(self):
        print(f"Starting musicpaper with {self.backend} backend...")
        last_matched_title = None

        while True:
            title, artist, playback_status = self.get_song_info()
            wallpaper_changed = False

            # restore wallpapers to normal after song ends
            if playback_status != 'Playing':
                if not self.using_default_wallpaper:
                    print("Playback stopped or paused, restoring original wallpaper")
                    self.restore_original_config()
                    last_matched_title = None
                time.sleep(self.config["general"]["check_interval"])
                continue

            if title:
                for song_name, wallpaper_name in self.expanded_song_wallpapers.items():
                    if song_name.lower() in title.lower():
                        if title != last_matched_title:
                            print(f"Matching song detected: {title} by {artist}")
                            if self.change_wallpaper(wallpaper_name):
                                print(f"Changed wallpaper for: {title}")
                                self.using_default_wallpaper = False
                                last_matched_title = title
                        wallpaper_changed = True
                        break

            if not wallpaper_changed and not self.using_default_wallpaper:
                print("No matching song playing, restoring original wallpaper")
                self.restore_original_config()
                last_matched_title = None

            time.sleep(self.config["general"]["check_interval"])

def main():
    monitor = MusicPaper()
    try:
        monitor.run()
    except KeyboardInterrupt:
        print("\nStopping musicpaper...")
        monitor.restore_original_config()

if __name__ == "__main__":
    main()
