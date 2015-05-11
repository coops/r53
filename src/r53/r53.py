#!/usr/bin/python

import argparse
import time
import logging
import os
import socket
import sys
import lxml.etree
from boto.route53 import Route53Connection

R53_API_VERSION = '2013-04-01'
R53_XMLNS = 'https://route53.amazonaws.com/doc/%s/' % R53_API_VERSION
XML_PARSER = lxml.etree.XMLParser(remove_blank_text=True)
XSLT_STRIPSPACE = lxml.etree.XSLT(lxml.etree.XML('''
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:strip-space elements="*"/>
</xsl:stylesheet>''', parser=XML_PARSER))

log = logging.getLogger('route53client')
log.setLevel(logging.DEBUG)

class ZoneNotFoundError(Exception):
  """Raised when unable to resolve a zone to its ID."""

def lookup_zone(conn, zone):
  """Look up a zone ID for a zone string.

  Args: conn: boto.route53.Route53Connection
        zone: string eg. foursquare.com
  Returns: zone ID eg. ZE2DYFZDWGSL4.
  Raises: ZoneNotFoundError if zone not found."""
  all_zones = conn.get_all_hosted_zones()
  for resp in all_zones['ListHostedZonesResponse']['HostedZones']:
    if resp['Name'].rstrip('.') == zone.rstrip('.'):
      return resp['Id'].replace('/hostedzone/', '')
  raise ZoneNotFoundError('zone %s not found in response' % zone)

def fetch_config(zone, conn):
  """Fetch all pieces of a Route 53 config from Amazon.

  Args: zone: string, hosted zone id.
        conn: boto.route53.Route53Connection
  Returns: list of ElementTrees, one for each piece of config."""
  more_to_fetch = True
  cfg_chunks = []
  next_name = None
  next_type = None
  next_identifier = None
  while more_to_fetch == True:
    more_to_fetch = False
    getstr = '/%s/hostedzone/%s/rrset' % (R53_API_VERSION, zone)
    if next_name is not None:
      getstr += '?name=%s&type=%s' % (next_name, next_type)
      if next_identifier is not None:
        getstr += '&identifier=%s' % next_identifier
    log.debug('requesting %s' % getstr)
    resp = conn.make_request('GET', getstr)
    etree = lxml.etree.parse(resp)
    cfg_chunks.append(etree)
    root = etree.getroot()
    truncated = root.find('{%s}IsTruncated' % R53_XMLNS)
    if truncated is not None and truncated.text == 'true':
      more_to_fetch = True
      next_name = root.find('{%s}NextRecordName' % R53_XMLNS).text
      next_type = root.find('{%s}NextRecordType' % R53_XMLNS).text
      try:
        next_identifier = root.find('{%s}NextRecordIdentifier' % R53_XMLNS).text
      except AttributeError:  # may not have next_identifier
        next_identifier = None
  return cfg_chunks

def merge_config(cfg_chunks):
  """Merge a set of fetched Route 53 config Etrees into a canonical form.

  Args: cfg_chunks: [ lxml.etree.ETree ]
  Returns: lxml.etree.Element"""
  root = lxml.etree.XML('<ResourceRecordSets xmlns="%s"></ResourceRecordSets>' % R53_XMLNS, parser=XML_PARSER)
  for chunk in cfg_chunks:
    for rrset in chunk.iterfind('.//{%s}ResourceRecordSet' % R53_XMLNS):
      root.append(rrset)
  return root

class InvalidArgumentException(Exception):
  pass

def normalize_rrs(rrsets):
  """Lexically sort the order of every ResourceRecord in a ResourceRecords
  element so we don't generate spurious changes: ordering of e.g. NS records
  is irrelevant to the DNS line protocol, but XML sees it differently.

  Also rewrite any wildcard records to use the ascii hex code: somewhere deep
  inside route53 is something that used to look like tinydns, and amazon's
  API will always display wildcard records as "\052.example.com".

  Args: rrsest: lxml.etree.Element (<ResourceRecordSets>) """
  for rrset in rrsets:
    if rrset.tag == '{%s}ResourceRecordSet' % R53_XMLNS:
      for rrs in rrset:
        # preformat wildcard records
        if rrs.tag == '{%s}Name' % R53_XMLNS:
          if rrs.text.startswith('*.'):
            old_text = rrs.text
            new_text = '\\052.%s' % old_text[2:]
            print 'Found wildcard record, rewriting to %s' % new_text
            rrs.text = rrs.text.replace(old_text, new_text)
        # sort ResourceRecord elements by Value
        if rrs.tag == '{%s}ResourceRecords' % R53_XMLNS:
          # 0th value of ResourceRecord is always the Value element
          sorted_rrs = sorted(rrs, key=lambda x: x[0].text)
          rrs[:] = sorted_rrs
  return rrsets

def generate_changeset(old, new, comment=None):
  """Diff two XML configs and return an object with changes to be written.

  Args: old, new: lxml.etree.Element (<ResourceRecordSets>).
  Returns: lxml.etree.ETree (<ChangeResourceRecordSetsRequest>) or None"""
  rrsets_tag = '{%s}ResourceRecordSets' % R53_XMLNS
  if rrsets_tag not in (old.tag, new.tag):
    log.error('both configs must be ResourceRecordSets tags. old: %s, new: %s' % (old.tag, new.tag))
    raise InvalidArgumentException()
  if comment is None:
    comment = 'Generated by %s for %s@%s at %s.' % (
        __file__,
        os.environ['USER'],
        socket.gethostname(),
        time.strftime('%Y-%m-%d %H:%M:%S'))
  root = lxml.etree.XML("""<ChangeResourceRecordSetsRequest xmlns="%s">
                        <ChangeBatch>
                          <Comment>%s</Comment>
                          <Changes/>
                        </ChangeBatch>
                        </ChangeResourceRecordSetsRequest>""" % (
      R53_XMLNS, comment), parser=XML_PARSER)
  changesroot = root.find('.//{%s}Changes' % R53_XMLNS)
  old = normalize_rrs(old)
  new = normalize_rrs(new)
  oldset = set([lxml.etree.tostring(x).rstrip() for x in old])
  newset = set([lxml.etree.tostring(x).rstrip() for x in new])
  if oldset == newset:
      return None
  # look for removed elements
  for rrs in old:
    rrsst = lxml.etree.tostring(rrs).rstrip()
    if rrsst not in newset:
      log.debug("REMOVED:")
      log.debug(rrsst)
      change = lxml.etree.XML('<Change xmlns="%s"><Action>DELETE</Action></Change>' % R53_XMLNS, parser=XML_PARSER)
      change.append(rrs)
      changesroot.append(change)
  # look for added elements
  for rrs in new:
    rrsst = lxml.etree.tostring(rrs).rstrip()
    if rrsst not in oldset:
      log.debug("ADDED:")
      log.debug(rrsst)
      change = lxml.etree.XML('<Change xmlns="%s"><Action>CREATE</Action></Change>' % R53_XMLNS, parser=XML_PARSER)
      change.append(rrs)
      changesroot.append(change)
  return root

def validate_changeset(changeset):
  """Validate a changeset is compatible with Amazon's API spec.

  Args: changeset: lxml.etree.Element (<ChangeResourceRecordSetsRequest>)
  Returns: [ errors ] list of error strings or []."""
  errors = []
  changes = changeset.findall('.//{%s}Change' % R53_XMLNS)
  num_changes = len(changes)
  if num_changes == 0:
    errors.append('changeset must have at least one <Change> element')
  if num_changes > 100:
    errors.append('changeset has %d <Change> elements: max is 100' % num_changes)
  rrs = changeset.findall('.//{%s}ResourceRecord' % R53_XMLNS)
  num_rrs = len(rrs)
  if num_rrs > 1000:
    errors.append('changeset has %d ResourceRecord elements: max is 1000' % num_rrs)
  values = changeset.findall('.//{%s}Value' % R53_XMLNS)
  num_chars = 0
  for value in values:
    num_chars += len(value.text)
  if num_chars > 10000:
    errors.append('changeset has %d chars in <Value> text: max is 10000' % num_chars)
  return errors

def normalize_xml(xml):
  """Normalize an XML object. Right now this only strips whitespace.

  Args: xml: lxml.tree.Element. Mutated by this function."""
  XSLT_STRIPSPACE(xml)


def main():
  parser = argparse.ArgumentParser(description='Push/pull Amazon Route 53 configs.')
  parser.add_argument('--push', metavar='file_to_push.xml', help="Push the config in this file to R53.")
  parser.add_argument('--pull', action='store_true', help="Dump current R53 config to stdout.")
  parser.add_argument('--confirm', action='store_true', help="Do not prompt before push.")
  parser.add_argument('--verbose', action='store_true')
  parser.add_argument('--zone', required=True, metavar="foursquare.com", help="Zone to push/pull.")
  args = parser.parse_args()

  ch = logging.StreamHandler()
  if args.verbose:
    ch.setLevel(logging.DEBUG)
  else:
    ch.setLevel(logging.INFO)
  log.addHandler(ch)

  if args.push == args.pull:
    print "You must specify either --push or --pull."
    sys.exit(1)

  # confirm wants stdin to itself
  if args.push == '-':
    args.confirm = True

  conn = Route53Connection()

  log.info('looking up zone for %s' % args.zone)
  zone_id = lookup_zone(conn, args.zone)
  log.info('fetching live config for zone %s' % zone_id)
  live_config = merge_config(fetch_config(zone_id, conn))

  if args.pull:
    print lxml.etree.tostring(live_config, pretty_print=True)

  if args.push:
    if args.push == '-':
        args.push = sys.stdin
    new_config = lxml.etree.parse(args.push)
    normalize_xml(live_config)
    normalize_xml(new_config.getroot())
    changeset = generate_changeset(live_config, new_config.getroot())
    if changeset is None:
        print "No changes found; exiting"
        sys.exit(0)
    changesetstr = lxml.etree.tostring(changeset, pretty_print=True)
    print "==CHANGESET=="
    print changesetstr
    errs = validate_changeset(changeset)
    if len(errs) > 0:
      print "changeset invalid. errors:"
      print '\n'.join(errs)
      print "exiting"
      sys.exit(1)
    if not args.confirm:
      ans = raw_input("Push y/N? ")
      if ans not in ['y', 'Y']:
        print "Confirmation failed; exiting"
        sys.exit(0)
    conn.change_rrsets(zone_id, changesetstr)

if __name__ == '__main__':
    main()
