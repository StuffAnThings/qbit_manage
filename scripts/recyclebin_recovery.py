#!/usr/bin/python3
import os
import shutil
import argparse
import sys

def move_files(src, dest, debug=True):
	"""Move files from source to destination"""
	dest_path = os.path.dirname(dest)
	if debug:
		print(f"From: {src} To: {dest}")
	else:
		if os.path.isdir(dest_path) is False:
			os.makedirs(dest_path, exist_ok=True)
		try:
			shutil.move(src, dest)
		except PermissionError as perm:
			print(perm)
		except FileNotFoundError as file:
			print(f"{file} : source: {src} -> destination: {dest}")
		except Exception as ex:
			print(ex)

def joiner(base, add):
	"""Join two paths together, just makes for less characters"""
	return os.path.join(base, add)

def ls(path):
	"""Kind of like bash ls, less characters"""
	return os.listdir(path)

if __name__ == "__main__":
	parser = argparse.ArgumentParser(
		prog='QBM_Recovery',
		description='Move files in the RecycleBin back into place',
		epilog='Don\'t forget to restart qbittorrent...'
	)
	parser.add_argument(
		'--debug',
		action="store_true",
		default=False,
		help="Print debug statements instead of taking action",
	)
	args = parser.parse_args()

	debug = args.debug
	base_dir = '/data/torrents/.RecycleBin'
	btbackup_dir = '/var/opt/docker/docker_configs/qbittorrent/config/data/BT_backup/'

	try:
		for dir in ls(base_dir): # torrents tv movies torrents_json links
			dir_path = joiner(base_dir, dir)
			if dir == 'torrents_json': # skip
				continue
			elif dir == 'torrents': # move as is
				for subdir in ls(dir_path):
					subdir_path = joiner(dir_path, subdir)
					move_files(subdir_path, btbackup_dir, debug)
			elif dir == 'links': # will have a subfolder
				for subdir in ls(dir_path):
					subdir_path = joiner(dir_path, subdir) # will be like /data/torrents/.RecycleBin/links/TorrentLeech
					for tdir in ls(subdir_path): # the action torrent files
						tdir_path = joiner(subdir_path, tdir)
						move_files(tdir_path, tdir_path.replace('/.RecycleBin', ''), debug)
			else: # movies tv
				for subdir in ls(dir_path):
					# might be a file, might be a folder
					subdir_path = joiner(dir_path, subdir)
					move_files(subdir_path, subdir_path.replace('/.RecycleBin', ''), debug)
		print("\n\nRemember to restart Qbittorent: docker compose restart qbittorrent")
	except KeyboardInterrupt:
		sys.exit(1)
