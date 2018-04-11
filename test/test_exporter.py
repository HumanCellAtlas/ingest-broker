import json
import mock
import time
import requests

from mock import MagicMock
from mock import Mock

from os import listdir
from os.path import isfile, join
from unittest import TestCase

from broker.ingestexportservice import IngestExporter
from broker import ingestexportservice
from broker import stagingapi



class TestExporter(TestCase):
    def test_bundleProject(self):
        # given:
        exporter = IngestExporter()
        project_entity = self._create_entity_template()

        # when:
        project_bundle = exporter.bundleProject(project_entity)

        # then:
        self.assertEqual(project_bundle['content'], project_entity['content'])
        self.assertEqual(project_bundle['schema_version'], exporter.schema_version)
        self.assertEqual(project_bundle['schema_type'], 'project_bundle')

        # and:
        schema_ref = project_bundle['describedBy']
        self.assertTrue(schema_ref.endswith('/project'))
        self.assertTrue(schema_ref.startswith(exporter.schema_url))

        # and:
        hca_ingest = project_bundle['hca_ingest']
        self.assertEqual(hca_ingest['submissionDate'], project_entity['submissionDate'])
        self.assertEqual(hca_ingest['updateDate'], project_entity['updateDate'])
        self.assertEqual(hca_ingest['document_id'], project_entity['uuid']['uuid'])
        self.assertEqual(hca_ingest['accession'], project_entity['accession'])

        # and:
        self.assertFalse('content' in hca_ingest.keys())

    def test_bundleFileIngest(self):
        # given:
        exporter = IngestExporter()
        file_entity = self._create_entity_template()

        # and:
        file_specific_details = {
            'fileName': 'SRR3934351_1.fastq.gz',
            'cloudUrl': 'https://sample.com/path/to/file',
            'checksums': [],
            'validationId': '62d900'
        }
        file_entity.update(file_specific_details)

        # when:
        file_ingest = exporter.bundleFileIngest(file_entity)

        # then:
        self.assertEqual(file_ingest['content'], file_entity['content'])

        # and:
        hca_ingest = file_ingest['hca_ingest']
        self.assertEqual(hca_ingest['document_id'], file_entity['uuid']['uuid'])
        self.assertEqual(hca_ingest['submissionDate'], file_entity['submissionDate'])
        # TODO is describedBy required?

    def test_bundleProtocolIngest(self):
        # given:
        exporter = IngestExporter()

        # and:
        protocol_entity = self._create_entity_template()

        # when:
        protocol_ingest = exporter.bundleProtocolIngest(protocol_entity)

        # then:
        self.assertEqual(protocol_ingest['content'], protocol_entity['content'])

        # and:
        hca_ingest = protocol_ingest['hca_ingest']
        self.assertEqual(hca_ingest['document_id'], protocol_entity['uuid']['uuid'])
        self.assertEqual(hca_ingest['submissionDate'], protocol_entity['submissionDate'])

    def test_get_project_info(self):
        # given:
        exporter = IngestExporter()

        # and:
        exporter.ingest_api.getRelatedEntities = MagicMock(return_value=['project1'])

        # when:
        process = {}
        project = exporter.get_project_info(process)

        # then:
        self.assertTrue(project)

    def test_get_project_info_error(self):
        # given:
        exporter = IngestExporter()

        # and:
        exporter.ingest_api.getRelatedEntities = MagicMock(return_value=['project1', 'project1'])
        process = {}

        # when, then:
        project = None
        with self.assertRaises(ingestexportservice.MultipleProjectsError) as e:
            project = exporter.get_project_info(process)

        self.assertFalse(project)

    def test_get_input_bundle(self):
        # given:
        exporter = IngestExporter()

        # and:
        exporter.ingest_api.getRelatedEntities = MagicMock(return_value=['bundle1', 'bundle2'])
        process = {}

        # when:
        input_bundle = exporter.get_input_bundle(process)

        # then:
        self.assertEqual('bundle1', input_bundle)

    def test_generate_metadata_files(self):
        # given:
        exporter = IngestExporter()

        # and:
        mock_bundle_content = {
            'project': {},
            'biomaterial': {},
            'process': {},
            'protocol': {},
            'file': {},
            'links': [],
        }
        exporter.build_and_validate_content = MagicMock(return_value=mock_bundle_content)
        process_info = ingestexportservice.ProcessInfo()
        process_info.input_bundle = None

        # when:
        metadata_files = exporter.generate_metadata_files(process_info)

        # then:
        self.assertEqual(metadata_files['project']['content'], mock_bundle_content['project'])
        self.assertEqual(metadata_files['biomaterial']['content'], mock_bundle_content['biomaterial'])
        self.assertEqual(metadata_files['process']['content'], mock_bundle_content['process'])
        self.assertEqual(metadata_files['protocol']['content'], mock_bundle_content['protocol'])
        self.assertEqual(metadata_files['file']['content'], mock_bundle_content['file'])
        self.assertEqual(metadata_files['links']['content'], mock_bundle_content['links'])

        self.assertEqual(metadata_files['project']['dss_uuid'], None)
        self.assertEqual(metadata_files['biomaterial']['dss_uuid'], None)
        self.assertEqual(metadata_files['process']['dss_uuid'], None)
        self.assertEqual(metadata_files['protocol']['dss_uuid'], None)
        self.assertEqual(metadata_files['file']['dss_uuid'], None)
        self.assertEqual(metadata_files['links']['dss_uuid'], None)

    def test_generate_metadata_files_has_input_bundle(self):
        # given:
        exporter = IngestExporter()

        # and:
        exporter.build_and_validate_content = MagicMock(return_value={
            'project': {},
            'biomaterial': {},
            'process': {},
            'protocol': {},
            'file': {},
            'links': [],
        })
        process_info = ingestexportservice.ProcessInfo()
        process_info.input_bundle = {
            'fileProjectMap': {
                'uuid': []
            }
        }

        # when:
        metadata_files = exporter.generate_metadata_files(process_info)

        # then:
        self.assertEqual(metadata_files['project']['dss_uuid'], 'uuid')
        self.assertEqual(metadata_files['biomaterial']['dss_uuid'], None)
        self.assertEqual(metadata_files['process']['dss_uuid'], None)
        self.assertEqual(metadata_files['protocol']['dss_uuid'], None)
        self.assertEqual(metadata_files['file']['dss_uuid'], None)
        self.assertEqual(metadata_files['links']['dss_uuid'], None)

    def test_upload_metadata_files(self):
        # given:
        exporter = IngestExporter()

        # and:
        file_desc = stagingapi.FileDescription('checksums', 'contentType', 'name', 'name', 'file_url')
        exporter.writeMetadataToStaging = MagicMock(return_value=file_desc)
        metadata_files_info = {
            'project': {
                'dss_filename': 'project.json',
                'dss_uuid': 'uuid',
                'content': {},
                'content_type': 'type'
            },
            'biomaterial': {
                'dss_uuid': None,
                'content': {},
                'content_type': 'type'
            },
            'process': {
                'dss_uuid': None,
                'content': {},
                'content_type': 'type'
            },
            'protocol': {
                'dss_uuid': None,
                'content': {},
                'content_type': 'type'
            },
            'file': {
                'dss_uuid': None,
                'content': {},
                'content_type': 'type'
            },
            'links': {
                'dss_uuid': None,
                'content': {},
                'content_type': 'type'
            }
        }

        # when:
        metadata_files = exporter.upload_metadata_files('sub_uuid', metadata_files_info)

        # then:
        self.assertEqual(metadata_files_info['project']['dss_uuid'], 'uuid')
        self.assertEqual(metadata_files_info['file']['upload_file_url'], 'file_url')

    def test_upload_metadata_files_error(self):
        # given:
        exporter = IngestExporter()

        # and:
        exporter.writeMetadataToStaging = Mock(side_effect=Exception('test upload file error'))
        metadata_files_info = {
            'project': {
                'dss_filename': 'project.json',
                'dss_uuid': 'uuid',
                'content': {},
                'content_type': 'type'
            },
            'biomaterial': {
                'dss_uuid': None,
                'content': {},
                'content_type': 'type'
            },
            'process': {
                'dss_uuid': None,
                'content': {},
                'content_type': 'type'
            },
            'protocol': {
                'dss_uuid': None,
                'content': {},
                'content_type': 'type'
            },
            'file': {
                'dss_uuid': None,
                'content': {},
                'content_type': 'type'
            },
            'links': {
                'dss_uuid': None,
                'content': {},
                'content_type': 'type'
            }
        }

        # when, then:
        with self.assertRaises(ingestexportservice.BundleFileUploadError) as e:
            metadata_files = exporter.upload_metadata_files('sub_uuid', metadata_files_info)

    def test_put_bundle_in_dss_error(self):
        # given:
        exporter = IngestExporter()

        # and:
        exporter.get_metadata_files = MagicMock(return_value=[])
        exporter.get_data_files = MagicMock(return_value=[])
        exporter.dss_api.createBundle = Mock(side_effect=Exception('test create bundle error'))

        # when, then:
        with self.assertRaises(ingestexportservice.BundleDSSError) as e:
            metadata_files = exporter.put_bundle_in_dss('bundle_uuid', {}, {})

    # TODO important!
    def test_recurse_process(self):
        pass

    # TODO this test uses submission_uuid = 'c2f94466-adee-4aac-b8d0-1e864fa5f8e8' is in integration env at the moment
    # use mock for this
    @mock.patch('broker.ingestexportservice.uuid.uuid4')
    def test_refactoring(self, mocked_uuid4):
        self.maxDiff = None
        mocked_uuid4.return_value = 'new-uuid'

        # given:
        exporter = IngestExporter()

        # and:
        submission_uuid = 'c2f94466-adee-4aac-b8d0-1e864fa5f8e8'
        process_ingest_url = 'http://api.ingest.integration.data.humancellatlas.org/processes/5abb9dd6b375bb0007c2bab0' #  the assay is a wrapper process

        ingestexportservice.uuid.uuid4 = MagicMock(return_value='new-uuid')

        # when:
        exporter.outputDir = './test/bundles/expected/'
        exporter.dryrun = True

        exporter.generateTestAssayBundle(submission_uuid, process_ingest_url)

        # use dry run and output dir for this test

        exporter.outputDir = './test/bundles/actual/'
        exporter.dryrun = True
        exporter.ingestUrl = 'http://api.ingest.integration.data.humancellatlas.org'

        start_time = time.time()

        exporter.export_bundle(submission_uuid, process_ingest_url)

        elapsed_time = time.time() - start_time

        print('export_bundle elapsed time:' + str(elapsed_time))

        # then:
        test_expected_bundles_dir = './test/bundles/expected/'
        test_actual_bundles_dir = './test/bundles/actual/'

        expected_files = [f for f in listdir(test_expected_bundles_dir) if isfile(join(test_expected_bundles_dir, f))]

        # TODO test only bundle manifest uuids for now
        expected_files = ['Mouse Melanoma_bundleManifest.json']

        for filename in expected_files:

            with open(test_expected_bundles_dir + filename) as expected_file:
                expected_file_json = json.loads(expected_file.read())

            with open(test_actual_bundles_dir + filename) as actual_file:
                actual_file_json = json.loads(actual_file.read())

            for property in expected_file_json.keys():
                self.assertEqual(list(expected_file_json[property].values()), list(actual_file_json.values()), "discrepancy in " + property)


    # transformation chain refers to the biomaterial/file -> process -> biomaterial/file paradigm used to represent
    # assay and analysis type procedures
    def test_transformation_chain_crawl(self):
        # mock the calls to the ingest API for the entities in the bundle
        get_requests_mock = mock()

        def mock_entities_url_to_file_dict():

            mock_entity_url_to_file_dict = dict()

            # wrapper process(lib prep -> sequencing)
            mock_entity_url_to_file_dict["processes/mock-assay-process-id"] = "/processes/wrapper_process_lib_prep_and_sequencing.json"
            mock_entity_url_to_file_dict["processes/mock-assay-process-id/chainedProcesses"] = "/processes/wrapper_process_lib_prep_and_sequencing_chained_processes.json"
            mock_entity_url_to_file_dict["processes/mock-assay-process-id/inputBiomaterials"] = "/processes/wrapper_process_lib_prep_and_sequencing_input_biomaterial.json"

            # lib prep process
            mock_entity_url_to_file_dict["processes/mock-lib-prep-process-id"] = "/processes/mock_lib_prep_process.json"

            # sequencing process
            mock_entity_url_to_file_dict["processes/mock-sequencing-process-id"] = "/processes/mock_sequencing_process.json"

            # cell suspension
            mock_entity_url_to_file_dict["biomaterials/mock-cell-suspension-id"] = "/biomaterials/mock_cell_suspension.json"
            mock_entity_url_to_file_dict["biomaterials/mock-cell-suspension-id/derivedByProcesses"] = "/biomaterials/mock_cell_suspension_derived_by_processes.json"

            # wrapper process(dissociation -> enrichment)
            mock_entity_url_to_file_dict["processes/mock-dissociation-enrichment-process-id"] = "/processes/wrapper_process_dissociation_and_enrichment.json"
            mock_entity_url_to_file_dict["processes/mock-dissociation-enrichment-process-id/chainedProcesses"] = "/processes/wrapper_process_lib_prep_and_sequencing_chained_processes.json"
            mock_entity_url_to_file_dict["processes/mock-dissociation-enrichment-process-id/inputBiomaterials"] = "/processes/wrapper_process_lib_prep_and_sequencing_input_biomaterial.json"

            # dissociation process
            mock_entity_url_to_file_dict["processes/mock-dissociation-process-id"] = "/processes/mock_dissociation_process.json"

            # enrichment process
            mock_entity_url_to_file_dict["processes/mock-enrichment-process-id"] = "/processes/mock_encrichment_process.json"

            # specimen
            mock_entity_url_to_file_dict["biomaterials/mock-specimen-id"] = "/biomaterials/mock_specimen.json"
            mock_entity_url_to_file_dict["biomaterials/mock-specimen-id/derivedByProcesses"] = "/biomaterials/mock_specimen_derived_by_processes.json"

            # sampling process
            mock_entity_url_to_file_dict["processes/mock-sampling-process-id"] = "/processes/mock_sampling_process.json"
            mock_entity_url_to_file_dict["processes/mock-sampling-process-id/inputBiomaterials"] = "/processes/mock_sampling_process_input_biomaterial.json"

            # donor
            mock_entity_url_to_file_dict["biomaterials/mock-donor-id"] = "/biomaterials/mock_donor.json"

            return mock_entity_url_to_file_dict





    def _create_entity_template(self):
        return {
            'submissionDate': '2018-03-14T09:53:02Z',
            'updateDate': '2018-03-14T09:53:02Z',
            'content': {},
            '_links': [],
            'events': [],
            'validationState': 'valid',
            'validationErrors': [],
            'uuid': {
                'uuid': '4674424e-3ab1-491c-8295-a68c7bb04b61'
            },
            'accession': 'accession123'
        }
