import os
import subprocess
import time

from django.conf import settings
from django.contrib.staticfiles.finders import find as static_finder

import jinja2
from jingo import register


try:
    from build import BUILD_ID_CSS, BUILD_ID_JS, BUILD_ID_IMG, BUNDLE_HASHES
except ImportError:
    BUILD_ID_CSS = BUILD_ID_JS = BUILD_ID_IMG = 'dev'
    BUNDLE_HASHES = {}


def get_media_root():
    """Return STATIC_ROOT or MEDIA_ROOT depending on JINGO_MINIFY_USE_STATIC.

    This allows projects using Django 1.4 to continue using the old
    ways, but projects using Django 1.4 to use the new ways.

    """
    if getattr(settings, 'JINGO_MINIFY_USE_STATIC', True):
        return settings.STATIC_ROOT
    return settings.MEDIA_ROOT


def get_media_url():
    """Return STATIC_URL or MEDIA_URL depending on JINGO_MINIFY_USE_STATIC.

    Allows projects using Django 1.4 to continue using the old ways
    but projects using Django 1.4 to use the new ways.

    """
    if getattr(settings, 'JINGO_MINIFY_USE_STATIC', True):
        return settings.STATIC_URL
    return settings.MEDIA_URL


def get_path(path):
    """Get a system path for a given file.

    This properly handles storing files in `project/app/static`, and any other
    location that Django's static files system supports.

    ``path`` should be relative to ``STATIC_ROOT``.

    """
    debug = getattr(settings, 'DEBUG', False)
    static = getattr(settings, 'JINGO_MINIFY_USE_STATIC', False)

    full_path = os.path.join(get_media_root(), path)

    if debug and static:
        found_path = static_finder(path)
        # If the path is not found by Django's static finder (like we are
        # trying to get an output path), it returns None, so fall back.
        if found_path is not None:
            full_path = found_path

    return full_path


def _get_item_path(item):
    """
    Determine whether to return a relative path or a URL.
    """
    if item.startswith(('//', 'http://', 'https://')):
        return item
    return get_media_url() + item


def _get_mtime(item):
    """Get a last-changed timestamp for development."""
    if item.startswith(('//', 'http://', 'https://')):
        return int(time.time())
    return int(os.path.getmtime(get_path(item)))


def _build_html(items, wrapping):
    """
    Wrap `items` in wrapping.
    """
    return jinja2.Markup('\n'.join((wrapping % (_get_item_path(item))
                                   for item in items)))


@register.function
def js(bundle, debug=settings.TEMPLATE_DEBUG, defer=False, async=False):
    """
    If we are in debug mode, just output a single script tag for each js file.
    If we are not in debug mode, return a script that points at bundle-min.js.
    """
    attrs = []

    if debug:
        # Add timestamp to avoid caching.
        items = ['%s?build=%s' % (item, _get_mtime(item)) for item in
                 settings.MINIFY_BUNDLES['js'][bundle]]
    else:
        build_id = BUILD_ID_JS
        bundle_full = "js:%s" % bundle
        if bundle_full in BUNDLE_HASHES:
            build_id = BUNDLE_HASHES[bundle_full]
        items = ('js/%s-min.js?build=%s' % (bundle, build_id,),)

    attrs.append('src="%s"')

    if defer:
        attrs.append('defer')

    if async:
        attrs.append('async')

    string = '<script %s></script>' % ' '.join(attrs)
    return _build_html(items, string)


@register.function
def css(bundle, media=False, debug=settings.TEMPLATE_DEBUG):
    """
    If we are in debug mode, just output a single script tag for each css file.
    If we are not in debug mode, return a script that points at bundle-min.css.
    """
    if not media:
        media = getattr(settings, 'CSS_MEDIA_DEFAULT', "screen,projection,tv")

    if debug:
        items = []
        for item in settings.MINIFY_BUNDLES['css'][bundle]:
            if (item.endswith('.less') and
                getattr(settings, 'LESS_PREPROCESS', False)):
                build_css(item, settings.LESS_BIN)
                items.append('%s.css' % item)
            elif (item.endswith(('.scss', '.sass')) and getattr(settings, 'SASS_BIN', False)):
                build_css(item, settings.SASS_BIN)
                items.append('%s.css' % item)
            else:
                items.append(item)

        # Add timestamp to avoid caching.
        items = ['%s?build=%s' % (item, _get_mtime(item)) for item in items]
    else:
        build_id = BUILD_ID_CSS
        bundle_full = "css:%s" % bundle
        if bundle_full in BUNDLE_HASHES:
            build_id = BUNDLE_HASHES[bundle_full]

        items = ('css/%s-min.css?build=%s' % (bundle, build_id,),)

    return _build_html(items,
            '<link rel="stylesheet" media="%s" href="%%s" />' % media)


def ensure_path_exists(path):
    try:
        os.makedirs(path)
    except OSError as e:
        # If the directory already exists, that is fine. Otherwise re-raise.
        if e.errno != os.errno.EEXIST:
            raise


def build_css(item, css_bin):
    """
    Builds LESS or Sass files. Takes path to lessc/sass binary as argument.
    """
    path_css = get_path('%s.css' % item)
    path_pre_css = get_path(item)

    updated_pre_css = os.path.getmtime(get_path(item))
    updated_css = 0  # If the file doesn't exist, force a refresh.
    if os.path.exists(path_css):
        updated_css = os.path.getmtime(path_css)

    # Is the uncompiled version newer?  Then recompile!
    if updated_pre_css > updated_css:
        ensure_path_exists(os.path.dirname(path_css))
        with open(path_css, 'w') as output:
            subprocess.Popen([css_bin, path_pre_css],
                             stdout=output)


def build_ids(request):
    """A context processor for injecting the css/js build ids."""
    return {'BUILD_ID_CSS': BUILD_ID_CSS, 'BUILD_ID_JS': BUILD_ID_JS,
            'BUILD_ID_IMG': BUILD_ID_IMG}
