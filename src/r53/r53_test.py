import lxml.etree
import mox
import unittest
import StringIO
from boto.route53 import Route53Connection
import r53

class Route53Test(unittest.TestCase):
  """Tests for functions in r53.py."""
  def setUp(self):
    self.r53mock = mox.MockObject(Route53Connection)

  def test_fetch_config(self):
    first_resp = StringIO.StringIO('''<?xml version="1.0" encoding="UTF-8"?>
<ListResourceRecordSetsResponse xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
   <ResourceRecordSets>
      <ResourceRecordSet>
         <Name>example.com.</Name>
         <Type>SOA</Type>
         <TTL>900</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>ns-2048.awsdns-64.net. hostmaster.awsdns.com. 1 7200 900 1209600 86400</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>
   <IsTruncated>true</IsTruncated>
   <MaxItems>1</MaxItems>
   <NextRecordName>testdoc2.example.com</NextRecordName>
   <NextRecordType>NS</NextRecordType>
   <NextRecordIdentifier>50</NextRecordIdentifier>
</ListResourceRecordSetsResponse>''')
    second_resp = StringIO.StringIO('''<?xml version="1.0" encoding="UTF-8"?>
<ListResourceRecordSetsResponse xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
   <ResourceRecordSets>
      <ResourceRecordSet>
         <Name>example.com.</Name>
         <Type>A</Type>
         <TTL>60</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>192.168.0.1</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>
   <IsTruncated>false</IsTruncated>
   <MaxItems>1</MaxItems>
   <NextRecordName>testdoc2.example.com</NextRecordName>
   <NextRecordType>NS</NextRecordType>
   <NextRecordIdentifier>50</NextRecordIdentifier>
</ListResourceRecordSetsResponse>''')
    expected_output = ['''<ListResourceRecordSetsResponse xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
    <ResourceRecordSets>
      <ResourceRecordSet>
         <Name>example.com.</Name>
         <Type>SOA</Type>
         <TTL>900</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>ns-2048.awsdns-64.net. hostmaster.awsdns.com. 1 7200 900 1209600 86400</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>
   <IsTruncated>true</IsTruncated>
   <MaxItems>1</MaxItems>
   <NextRecordName>testdoc2.example.com</NextRecordName>
   <NextRecordType>NS</NextRecordType>
   <NextRecordIdentifier>50</NextRecordIdentifier>
</ListResourceRecordSetsResponse>''',
                       '''<ListResourceRecordSetsResponse xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
    <ResourceRecordSets>
      <ResourceRecordSet>
         <Name>example.com.</Name>
         <Type>A</Type>
         <TTL>60</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>192.168.0.1</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>
   <IsTruncated>false</IsTruncated>
   <MaxItems>1</MaxItems>
   <NextRecordName>testdoc2.example.com</NextRecordName>
   <NextRecordType>NS</NextRecordType>
   <NextRecordIdentifier>50</NextRecordIdentifier>
   </ListResourceRecordSetsResponse>''']
    expected_output = [lxml.etree.XML(x) for x in expected_output]
    zone = 'AAAA'
    self.r53mock.make_request('GET', '/2013-04-01/hostedzone/%s/rrset' % zone).AndReturn(first_resp)
    self.r53mock.make_request('GET',
      '/2013-04-01/hostedzone/%s/rrset?name=testdoc2.example.com&type=NS&identifier=50' % zone).AndReturn(second_resp)
    mox.Replay(self.r53mock)
    chunks = r53.fetch_config(zone, self.r53mock)
    for x in chunks:
        r53.XSLT_STRIPSPACE(x)
    for x in expected_output:
        r53.XSLT_STRIPSPACE(x)
    self.assertEqual([lxml.etree.tostring(x.getroot()) for x in chunks], [lxml.etree.tostring(x) for x in expected_output])
    mox.Verify(self.r53mock)

  def test_changeset_replace(self):
    old = lxml.etree.XML('''<ResourceRecordSets xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
      <ResourceRecordSet>
         <Name>example.com.</Name>
         <Type>SOA</Type>
         <TTL>900</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>ns-2048.awsdns-64.net. hostmaster.awsdns.com. 1 7200 900 1209600 86400</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>''')
    new = lxml.etree.XML('''<ResourceRecordSets xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
      <ResourceRecordSet>
         <Name>example.com.</Name>
         <Type>A</Type>
         <TTL>60</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>192.168.0.1</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>''')
    expected_output = lxml.etree.XML(
        '''<ChangeResourceRecordSetsRequest xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
          <ChangeBatch>
            <Comment>foobar</Comment>
            <Changes>
              <Change>
                <Action>DELETE</Action>
                <ResourceRecordSet>
                  <Name>example.com.</Name>
                  <Type>SOA</Type>
                  <TTL>900</TTL>
                  <ResourceRecords>
                    <ResourceRecord>
                      <Value>ns-2048.awsdns-64.net. hostmaster.awsdns.com. 1 7200 900 1209600 86400</Value>
                    </ResourceRecord>
                  </ResourceRecords>
                </ResourceRecordSet>
              </Change>
              <Change>
                <Action>CREATE</Action>
                <ResourceRecordSet>
                  <Name>example.com.</Name>
                  <Type>A</Type>
                  <TTL>60</TTL>
                  <ResourceRecords>
                    <ResourceRecord>
                      <Value>192.168.0.1</Value>
                    </ResourceRecord>
                  </ResourceRecords>
                </ResourceRecordSet>
              </Change>
            </Changes>
          </ChangeBatch>
        </ChangeResourceRecordSetsRequest>''')
    changeset = r53.generate_changeset(old, new, comment='foobar')
    r53.XSLT_STRIPSPACE(changeset)
    r53.XSLT_STRIPSPACE(expected_output)
    self.assertEqual(lxml.etree.tostring(changeset), lxml.etree.tostring(expected_output))

  def test_changeset_add(self):
    old = lxml.etree.XML('''<ResourceRecordSets xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
      <ResourceRecordSet>
         <Name>example.com.</Name>
         <Type>SOA</Type>
         <TTL>900</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>ns-2048.awsdns-64.net. hostmaster.awsdns.com. 1 7200 900 1209600 86400</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>''')
    new = lxml.etree.XML('''<ResourceRecordSets xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
      <ResourceRecordSet>
         <Name>example.com.</Name>
         <Type>SOA</Type>
         <TTL>900</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>ns-2048.awsdns-64.net. hostmaster.awsdns.com. 1 7200 900 1209600 86400</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
      <ResourceRecordSet>
         <Name>example.com.</Name>
         <Type>A</Type>
         <TTL>60</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>192.168.0.1</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>''')
    expected_output = lxml.etree.XML(
        '''<ChangeResourceRecordSetsRequest xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
          <ChangeBatch>
            <Comment>foobar</Comment>
            <Changes>
              <Change>
                <Action>CREATE</Action>
                <ResourceRecordSet>
                  <Name>example.com.</Name>
                  <Type>A</Type>
                  <TTL>60</TTL>
                  <ResourceRecords>
                    <ResourceRecord>
                      <Value>192.168.0.1</Value>
                    </ResourceRecord>
                  </ResourceRecords>
                </ResourceRecordSet>
              </Change>
            </Changes>
          </ChangeBatch>
        </ChangeResourceRecordSetsRequest>''')
    changeset = r53.generate_changeset(old, new, comment='foobar')
    r53.XSLT_STRIPSPACE(changeset)
    r53.XSLT_STRIPSPACE(expected_output)
    self.assertEqual(lxml.etree.tostring(changeset), lxml.etree.tostring(expected_output))

  def test_changeset_subtract(self):
    parser = lxml.etree.XMLParser(remove_blank_text=True)
    old = lxml.etree.XML('''<ResourceRecordSets xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
      <ResourceRecordSet>
         <Name>example.com.</Name>
         <Type>SOA</Type>
         <TTL>900</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>ns-2048.awsdns-64.net. hostmaster.awsdns.com. 1 7200 900 1209600 86400</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
      <ResourceRecordSet>
         <Name>example.com.</Name>
         <Type>A</Type>
         <TTL>60</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>192.168.0.1</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>''', parser=parser)
    new = lxml.etree.XML('''<ResourceRecordSets xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
      <ResourceRecordSet>
         <Name>example.com.</Name>
         <Type>SOA</Type>
         <TTL>900</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>ns-2048.awsdns-64.net. hostmaster.awsdns.com. 1 7200 900 1209600 86400</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>''', parser=parser)
    expected_output = lxml.etree.XML(
        '''<ChangeResourceRecordSetsRequest xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
          <ChangeBatch>
            <Comment>foobar</Comment>
            <Changes>
              <Change>
                <Action>DELETE</Action>
                <ResourceRecordSet>
                  <Name>example.com.</Name>
                  <Type>A</Type>
                  <TTL>60</TTL>
                  <ResourceRecords>
                    <ResourceRecord>
                      <Value>192.168.0.1</Value>
                    </ResourceRecord>
                  </ResourceRecords>
                </ResourceRecordSet>
              </Change>
            </Changes>
          </ChangeBatch>
        </ChangeResourceRecordSetsRequest>''', parser=parser)
    changeset = r53.generate_changeset(old, new, comment='foobar')
    self.assertEqual(lxml.etree.tostring(changeset), lxml.etree.tostring(expected_output))

  def test_changeset_null(self):
    parser = lxml.etree.XMLParser(remove_blank_text=True)
    old = lxml.etree.XML('''<ResourceRecordSets xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
      <ResourceRecordSet>
         <Name>example.com.</Name>
         <Type>SOA</Type>
         <TTL>900</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>ns-2048.awsdns-64.net. hostmaster.awsdns.com. 1 7200 900 1209600 86400</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>''', parser=parser)
    new = lxml.etree.XML('''<ResourceRecordSets xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
      <ResourceRecordSet>
         <Name>example.com.</Name>
         <Type>SOA</Type>
         <TTL>900</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>ns-2048.awsdns-64.net. hostmaster.awsdns.com. 1 7200 900 1209600 86400</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>''', parser=parser)
    self.assertEqual(r53.generate_changeset(old, new), None)

  def test_changeset_wildcard(self):
    parser = lxml.etree.XMLParser(remove_blank_text=True)
    old = lxml.etree.XML('''<ResourceRecordSets xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
      <ResourceRecordSet>
         <Name>\052.example.com.</Name>
         <Type>A</Type>
         <TTL>60</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>192.168.0.1</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>''', parser=parser)
    new = lxml.etree.XML('''<ResourceRecordSets xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
      <ResourceRecordSet>
         <Name>*.example.com.</Name>
         <Type>A</Type>
         <TTL>60</TTL>
         <ResourceRecords>
            <ResourceRecord>
               <Value>192.168.0.1</Value>
            </ResourceRecord>
         </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>''', parser=parser)
    self.assertEqual(r53.generate_changeset(old, new), None)

  def test_normalize_rrs(self):
    parser = lxml.etree.XMLParser(remove_blank_text=True)
    old = lxml.etree.XML('''<ResourceRecordSets xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
      <ResourceRecordSet>
        <Name>example.com.</Name>
        <Type>NS</Type>
        <TTL>172800</TTL>
        <ResourceRecords>
          <ResourceRecord>
            <Value>ns1.example.com.</Value>
          </ResourceRecord>
          <ResourceRecord>
            <Value>ns2.example.com.</Value>
          </ResourceRecord>
          <ResourceRecord>
            <Value>ns3.example.com.</Value>
          </ResourceRecord>
        </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>''', parser=parser)
    new = lxml.etree.XML('''<ResourceRecordSets xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
      <ResourceRecordSet>
        <Name>example.com.</Name>
        <Type>NS</Type>
        <TTL>172800</TTL>
        <ResourceRecords>
          <ResourceRecord>
            <Value>ns2.example.com.</Value>
          </ResourceRecord>
          <ResourceRecord>
            <Value>ns3.example.com.</Value>
          </ResourceRecord>
          <ResourceRecord>
            <Value>ns1.example.com.</Value>
          </ResourceRecord>
        </ResourceRecords>
      </ResourceRecordSet>
   </ResourceRecordSets>''', parser=parser)
    sorted_old = r53.normalize_rrs(old)
    sorted_new = r53.normalize_rrs(new)
    self.assertEqual(lxml.etree.tostring(sorted_old),
                     lxml.etree.tostring(sorted_new))


if __name__ == '__main__':
    unittest.main()
