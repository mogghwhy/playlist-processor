#!/usr/bin/env python3
import argparse
import json
import os
from urllib.parse import parse_qs, urlparse

# --- Configuration Loading ---
def load_config(config_file):
    with open(config_file, 'r') as f:
        return json.load(f)

# --- Utility Functions ---
def load_metadata(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def list_video_sizes(metadata):
    print("Available video sizes (width x height):")
    for video in metadata.get("video", []):
        print(f"{video['width']}x{video['height']}")

def list_audio_codecs(metadata):
    print("Available audio (codec, bitrate) pairs:")
    for audio in metadata.get("audio", []):
        print(f"{audio['codecs']} @ {audio['bitrate']}bps")

def decode_init_segment_bash(init_segment, output_filename):
    return f"echo '{init_segment}' | base64 --decode > {output_filename}"

def parse_segment_url(segment_url):
    parsed = urlparse(f"https://dummy.com/{segment_url}")
    query = parse_qs(parsed.query)
    range_header = query.get("range", [""])[0]
    pathsig = query.get("pathsig", [""])[0]
    return parsed.path.strip("/"), pathsig, range_header

def generate_curl_command(
    base_url,
    pathsig,
    range_header,
    exp,
    acl,
    hmac,
    file_path,
    seq,
    referer,
    user_agent,
    origin,
    output_dir
):
    url = (
        f"{base_url}/exp={exp}~acl={acl}~hmac={hmac}/{file_path}"
        f"?pathsig={pathsig}&r=dXMtZWFzdDE%3D&range={range_header}"
    )

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,lv;q=0.8,no;q=0.7",
        "origin": origin,
        "priority": "u=1, i",
        "referer": referer,
        "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": user_agent
    }

    header_str = " \\\n".join(f"-H '{k}: {v}'" for k, v in headers.items())
    output_file = os.path.join(output_dir, f"segment_{seq:04}.mp4")
    curl_cmd = f"curl '{url}' \\\n{header_str} -o {output_file}"
    return curl_cmd

def generate_segment_commands(base_url, index_segment, segments, exp, acl, hmac, file_path_prefix, output_dir, referer, user_agent, origin):
    lines = []
    file_list = []

    # Index segment
    file_path, pathsig, range_header = parse_segment_url(index_segment)
    index_filename = os.path.join(output_dir, f"segment_0000.mp4")
    lines.append("# Index segment")
    lines.append(generate_curl_command(base_url, pathsig, range_header, exp, acl, hmac, file_path_prefix + file_path, seq=0, referer=referer, user_agent=user_agent, origin=origin, output_dir=output_dir))
    lines.append("")
    file_list.append(index_filename)

    # Media segments
    lines.append("# Media segments")
    for i, segment in enumerate(segments, start=1):
        file_path, pathsig, range_header = parse_segment_url(segment["url"])
        segment_path = os.path.join(output_dir, f"segment_{i:04}.mp4")
        lines.append(generate_curl_command(base_url, pathsig, range_header, exp, acl, hmac, file_path_prefix + file_path, seq=i, referer=referer, user_agent=user_agent, origin=origin, output_dir=output_dir))
        file_list.append(segment_path)

    return lines, file_list

def write_bash_script(commands, output_file):
    with open(output_file, 'w') as f:
        f.write("#!/bin/bash\n\n")
        for line in commands:
            f.write(line + "\n")

def write_ffmpeg_list(file_list, list_path):
    with open(list_path, 'w') as f:
        for path in file_list:
            f.write(f"file '{path}'\n")

def ensure_output_dir(path):
    os.makedirs(path, exist_ok=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--option", type=int, required=True, choices=[1, 2, 3, 4])
    parser.add_argument("--video-size", help="e.g., 426x228")
    parser.add_argument("--codec", help="Audio codec, e.g., avc1.640015")
    parser.add_argument("--bitrate", help="Audio bitrate, e.g., 239000")
    parser.add_argument("--file", default="playlist-playlist.json")
    parser.add_argument("--output", default="output.sh")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--output-dir", default="segments")
    parser.add_argument("--ffmpeg-list", default="segments/ffmpeg.txt")

    args = parser.parse_args()

    config = load_config(args.config)
    metadata = load_metadata(args.file)

    base_url = config["base_url"]
    exp = config["exp"]
    hmac = config["hmac"]
    referer = config["referer"]
    user_agent = config["user_agent"]
    origin = config["origin"]
    acl = f"%2F{metadata['clip_id']}%2F%2A"
    file_path_prefix = f"{metadata['clip_id']}{config['file_path_postfix']}"

    ensure_output_dir(args.output_dir)

    if args.option == 1:
        list_video_sizes(metadata)
        return

    if args.option == 3:
        list_audio_codecs(metadata)
        return

    bash_lines = []
    file_list = []

    if args.option == 2:
        if not args.video_size:
            print("Error: --video-size is required for option 2")
            return
        width, height = map(int, args.video_size.lower().split("x"))
        for video in metadata.get("video", []):
            if video["width"] == width and video["height"] == height:
                init_filename = os.path.join(args.output_dir, f"{video['id']}_init.mp4")
                bash_lines.append("# Decode init_segment")
                bash_lines.append(decode_init_segment_bash(video["init_segment"], init_filename))
                bash_lines.append("")
                file_list.append(init_filename)
                cmd_lines, segment_files = generate_segment_commands(base_url, video["index_segment"], video["segments"], exp, acl, hmac, file_path_prefix, args.output_dir, referer, user_agent, origin)
                bash_lines += cmd_lines
                file_list += segment_files
                break
        else:
            print("Video size not found.")
            return

    elif args.option == 4:
        if not args.codec or not args.bitrate:
            print("Error: --codec and --bitrate are required for option 4")
            return
        for audio in metadata.get("audio", []):
            if audio["codecs"] == args.codec and str(audio["bitrate"]) == args.bitrate:
                init_filename = os.path.join(args.output_dir, f"{audio['id']}_init.mp4")
                bash_lines.append("# Decode init_segment")
                bash_lines.append(decode_init_segment_bash(audio["init_segment"], init_filename))
                bash_lines.append("")
                file_list.append(init_filename)
                cmd_lines, segment_files = generate_segment_commands(base_url, audio["index_segment"], audio["segments"], exp, acl, hmac, file_path_prefix, args.output_dir, referer, user_agent, origin)
                bash_lines += cmd_lines
                file_list += segment_files
                break
        else:
            print("Audio stream not found.")
            return
    if args.option == 2 or args.option == 4:
        write_bash_script(bash_lines, args.output)
        write_ffmpeg_list(file_list, args.ffmpeg_list)
        print(f"Bash script written to {args.output}")
        print(f"FFmpeg concat list written to {args.ffmpeg_list}")

if __name__ == "__main__":
    main()
