import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from publisher import Publisher, guide_id
PNG=b'\x89PNG\r\n\x1a\n' + b'fake image bytes'
SAMPLE='''<h1 class="scribe-title">Report Spam in Gmail</h1><p class="scribe-author"><a href="https://scribehow.com">Author</a></p><div class="scribe-step"><p class="scribe-step-text">1. Select email</p></div><p class="scribe-screenshot-container"><img src="https://example.com/image.png" alt="Screenshot"></p><h4 class="scribe-footer">Made with Scribe</h4>'''
class Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); root=Path(self.temp.name); self.exports=root/'exports'; self.exports.mkdir(); self.output=root/'out'; self.fetch=lambda u,p:(PNG,'.png'); self.pub=Publisher(self.exports,self.output,fetch=self.fetch); self.file=self.exports/'Spam.html'; self.file.write_text(SAMPLE)
 def tearDown(self):self.temp.cleanup()
 def test_publish_update_unpublish_and_durable_notice(self):
  self.pub.publish(self.file); page=(self.output/'spam.html').read_text(encoding='utf-8'); self.assertIn('Report Spam in Gmail',page); self.assertNotIn('scribehow.com',page); self.assertIn('images/spam/image-001.png',page); self.assertEqual((self.output/'images/spam/image-001.png').read_bytes(),PNG); self.assertIn('spam.html',(self.output/'index.html').read_text(encoding='utf-8'))
  self.file.write_text(SAMPLE.replace('Report Spam in Gmail','Updated title')); self.pub.publish(self.file); self.assertIn('Updated title',(self.output/'index.html').read_text(encoding='utf-8'))
  self.pub.unpublish('spam'); self.assertFalse((self.output/'spam.html').exists()); self.assertFalse((self.output/'images/spam').exists()); self.assertNotIn('spam.html',(self.output/'index.html').read_text(encoding='utf-8')); self.assertEqual(Publisher(self.exports,self.output).state['removals'],['spam.html','images/spam/']); self.assertTrue(self.file.exists())
 def test_failed_image_retains_previous(self):
  self.pub.publish(self.file); old=(self.output/'spam.html').read_bytes(); self.pub.fetch=lambda *a: (_ for _ in ()).throw(ValueError('download failed')); self.file.write_text(SAMPLE.replace('Select email','changed'))
  with self.assertRaises(ValueError):self.pub.publish(self.file)
  self.assertEqual((self.output/'spam.html').read_bytes(),old)
 def test_sanitizes_script_and_active_html(self):
  self.file.write_text('<h1>Title</h1><script>alert(1)</script><iframe src="https://evil"></iframe><p onclick="bad()" style="x">Safe <a href="javascript:bad()">Link</a></p>'); self.pub.publish(self.file); page=(self.output/'spam.html').read_text(encoding='utf-8'); self.assertNotIn('alert(1)',page); self.assertNotIn('iframe',page); self.assertNotIn('onclick',page); self.assertNotIn('javascript:',page); self.assertIn('Safe',page)
 def test_collision_and_foreign_files(self):
  (self.exports/'spam!.html').write_text(SAMPLE)
  with self.assertRaises(ValueError):self.pub.publish(self.file)
  (self.exports/'spam!.html').unlink(); self.output.mkdir(); (self.output/'spam.html').write_text('do not change')
  with self.assertRaises(ValueError):self.pub.publish(self.file)
  self.assertEqual((self.output/'spam.html').read_text(),'do not change')
 def test_relative_image_traversal_rejected(self):
  self.file.write_text('<h1>A</h1><img src="../secret.png">'); self.pub.fetch=__import__('publisher').download_image
  with self.assertRaises(ValueError):self.pub.publish(self.file)
 def test_output_ownership_and_foreign_images(self):
  self.output.mkdir(); (self.output/'index.html').write_text('existing')
  with self.assertRaises(ValueError): self.pub.publish(self.file)
  self.assertEqual((self.output/'index.html').read_text(),'existing')
  (self.output/'index.html').unlink(); self.pub.publish(self.file)
  (self.output/'images/spam/notes.txt').write_text('keep')
  with self.assertRaises(ValueError): self.pub.unpublish('spam')
  with self.assertRaises(ValueError): self.pub.publish(self.file)
  self.assertTrue((self.output/'images/spam/notes.txt').exists())
 def test_reserved(self):
  with self.assertRaises(ValueError):guide_id('index.html')
 def test_save_pasted_export_then_publish(self):
  source=self.pub.save_pasted_export('Pasted Guide.html', SAMPLE)
  self.assertEqual(source, self.exports/'Pasted Guide.html')
  self.assertEqual(source.read_text(encoding='utf-8'), SAMPLE)
  self.pub.publish(source)
  self.assertTrue((self.output/'pasted-guide.html').exists())
  self.assertIn('pasted-guide.html', (self.output/'index.html').read_text(encoding='utf-8'))
 def test_save_pasted_export_rejects_paths_empty_and_links(self):
  for name, content in (('../escape.html','<h1>A</h1>'), ('guide.txt','<h1>A</h1>'), ('empty.html','   ')):
   with self.subTest(name=name):
    with self.assertRaises(ValueError): self.pub.save_pasted_export(name,content)
  target=self.exports/'target.html'; target.write_text('keep')
  link=self.exports/'linked.html'
  try: link.symlink_to(target)
  except (OSError,NotImplementedError): self.skipTest('symbolic links not available')
  with self.assertRaises(ValueError): self.pub.save_pasted_export('linked.html','<h1>A</h1>')
  self.assertEqual(target.read_text(),'keep')
 def test_failed_index_update_rolls_back(self):
  import publisher
  self.pub.publish(self.file)
  oldpage=(self.output/'spam.html').read_bytes(); oldindex=(self.output/'index.html').read_bytes()
  self.file.write_text(SAMPLE.replace('Report Spam in Gmail','Changed title'))
  original=publisher.atomic_write; failed=False
  def fail_once(path,data):
   nonlocal failed
   if path.name=='guide-style.css' and not failed:
    failed=True; raise OSError('simulated failure')
   return original(path,data)
  with patch('publisher.atomic_write',side_effect=fail_once):
   with self.assertRaises(OSError): self.pub.publish(self.file)
  self.assertEqual(oldpage,(self.output/'spam.html').read_bytes()); self.assertEqual(oldindex,(self.output/'index.html').read_bytes())
  self.assertEqual(self.pub.state['guides']['spam']['title'],'Report Spam in Gmail')
 def test_failed_unpublish_rolls_back(self):
  import publisher
  self.pub.publish(self.file); oldindex=(self.output/'index.html').read_bytes()
  original=publisher.atomic_write; failed=False
  def fail_once(path,data):
   nonlocal failed
   if path.name=='guide-style.css' and not failed:
    failed=True; raise OSError('simulated failure')
   return original(path,data)
  with patch('publisher.atomic_write',side_effect=fail_once):
   with self.assertRaises(OSError): self.pub.unpublish('spam')
  self.assertTrue((self.output/'spam.html').exists()); self.assertTrue((self.output/'images/spam/image-001.png').exists())
  self.assertEqual(oldindex,(self.output/'index.html').read_bytes()); self.assertIn('spam',self.pub.state['guides'])
 def test_disallow_untrusted_remote_image_hosts(self):
  from publisher import download_image
  for url in ('http://colony-recorder.s3.us-west-1.amazonaws.com/image.png','https://localhost/secret','https://169.254.169.254/','https://example.com/a'):
   with self.subTest(url=url):
    with self.assertRaises(ValueError): download_image(url,self.exports)
 def test_disallow_redirect_to_untrusted_host(self):
  from publisher import SafeRedirect
  import urllib.request
  req=urllib.request.Request('https://colony-recorder.s3.us-west-1.amazonaws.com/x')
  with self.assertRaises(ValueError): SafeRedirect().redirect_request(req,None,302,'Found',{},'http://127.0.0.1/')
 def test_linked_managed_file_is_rejected(self):
  self.pub.publish(self.file)
  target=self.exports/'important'; target.write_text('retain')
  (self.output/'spam.html').unlink()
  try: (self.output/'spam.html').symlink_to(target)
  except (OSError,NotImplementedError): self.skipTest('symbolic links not available')
  with self.assertRaises(ValueError): self.pub.unpublish('spam')
  self.assertEqual(target.read_text(),'retain')
if __name__=='__main__':unittest.main()
