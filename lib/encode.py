import os
import sys
import wave
import time
import argparse
import subprocess
from tqdm import tqdm
from sfzparser import SFZFile, Group
from wavio import read_wave_file
from utils import group_by_attr, note_name, full_path


def length_of(filename):
    return wave.open(filename).getnframes()


def create_flac(concat_filename, output_filename):
    if os.path.exists(output_filename):
        return True

    commandline = [
        'ffmpeg',
        '-y',
        '-f',
        'concat',
        '-safe',
        '0',
        '-i',
        concat_filename,
        '-codec:a',
        'flac',
        '-compression_level', '12',
        output_filename
    ]
    # sys.stderr.write("Calling '%s'...\n" % ' '.join(commandline))
    subprocess.call(
        commandline,
        stdout=open('/dev/null', 'w'),
        stderr=open('/dev/null', 'w'),
        stdin=open('/dev/null', 'r'),
    )


def create_ogg(concat_filename, output_filename, quality=5):
    if os.path.exists(output_filename):
        return True

    commandline = [
        'ffmpeg',
        '-y',
        '-f',
        'concat',
        '-safe',
        '0',
        '-i',
        concat_filename,
        '-codec:a',
        'libvorbis',
        '-qscale:a',
        str(quality),
        output_filename
    ]
    # sys.stderr.write("Calling '%s'...\n" % ' '.join(commandline))
    subprocess.call(
        commandline,
        stdout=open('/dev/null', 'w'),
        stderr=open('/dev/null', 'w')
    )


def flacize_after_sampling(
    output_folder,
    groups,
    sfzfile,
    cleanup_aif_files=True
):
    new_groups = []

    old_paths_to_unlink = [
        full_path(output_folder, r.attributes['sample'])
        for group in groups
        for r in group.regions
    ]

    for group in groups:
        # Make one FLAC file per key, to get more compression.
        output = sum([list(concat_samples(
                           key_regions, output_folder, note_name(key)
                           ))
                      for key, key_regions in
                      group_by_attr(group.regions, [
                          'key', 'pitch_keycenter'
                      ]).iteritems()], [])
        new_groups.append(Group(group.attributes, output))

    with open(sfzfile + '.flac.sfz', 'w') as file:
        file.write("\n".join([str(group) for group in new_groups]))

    if cleanup_aif_files:
        for path in old_paths_to_unlink:
            try:
                os.unlink(path)
            except OSError as e:
                print "Could not unlink path: %s: %s" % (path, e)


ANTI_CLICK_OFFSET = 3


def concat_samples(regions, path, name=None, extension=None, quality=None):
    if extension is None:
        raise ValueError('Expected extension!')
    if extension == 'ogg' and quality is None:
        raise ValueError('ogg requires a quality field')

    if name is None:
        output_filename = 'all_samples_%f.%s' % (time.time(), extension)
    else:
        output_filename = '%s.%s' % (name, extension)

    concat_filename = 'concat.txt'

    with open(concat_filename, 'w') as outfile:
        global_offset = 0
        for region in regions:
            sample = region.attributes['sample']

            sample_data = read_wave_file(full_path(path, sample))

            sample_length = len(sample_data[0])
            region.attributes['offset'] = global_offset
            region.attributes['end'] = (
                global_offset + sample_length - ANTI_CLICK_OFFSET
            )
            # TODO: make sure endpoint is a zero crossing to prevent clicks
            region.attributes['sample'] = output_filename
            outfile.write("file '%s'\n" % full_path(path, sample))
            global_offset += sample_length

    if extension == 'flac':
        create_flac(concat_filename, full_path(path, output_filename))
    elif extension == 'ogg':
        create_ogg(concat_filename, full_path(path, output_filename), quality)

    os.unlink(concat_filename)

    return regions


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='encode SFZ files into other formats'
    )
    parser.add_argument('files', type=str, help='files to process', nargs='+')
    parser.add_argument(
        '--format',
        dest='format',
        action='store',
        choices=['flac', 'ogg'],
        default='flac',
        help='Codec to encode to',
    )
    parser.add_argument(
        '--quality',
        dest='quality',
        action='store',
        default=5,
        help='Quality params for ffmpeg (only used for ogg)',
    )
    parser.add_argument(
        '--sprite-mode',
        dest='sprite_mode',
        action='store',
        choices=['sample', 'key', 'all'],
        help='Sprite mode to help with compression.',
        default='key',
    )
    args = parser.parse_args()

    for filename in args.files:
        all_groups = SFZFile(open(filename).read()).groups

        if args.sprite_mode == 'all':
            output = list(
                concat_samples(
                    sum([group.regions for group in all_groups], []),
                    filename,
                    'all',
                    args.format,
                    args.quality))

        for group in all_groups:
            # Make one FLAC file per key, to get more compression.
            if args.sprite_mode == 'key':
                output = sum([list(concat_samples(regions,
                                                  filename,
                                                  note_name(key),
                                                  args.format,
                                                  args.quality))
                              for key, regions in
                              tqdm(group_by_attr(group.regions,
                                                 ['pitch_keycenter', 'key']
                                                 ).items())], [])
            elif args.sprite_mode == 'sample':
                output = sum([list(concat_samples(
                    regions,
                    filename,
                    note_name(region.attributes['key']),
                    args.format,
                    args.quality)) for region in tqdm(group.regions)], [])
            print group.just_group()

            # Regions should have been modified in place
            for region in group.regions:
                print region
