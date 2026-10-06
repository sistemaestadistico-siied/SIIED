"""
Management command to run automatic data validations.
"""
from django.core.management.base import BaseCommand
from indicadores.data_validation import run_automatic_validations
from indicadores.models import Indicador
import json


class Command(BaseCommand):
    help = 'Run automatic data validations for indicators'

    def add_arguments(self, parser):
        parser.add_argument(
            '--indicator',
            type=int,
            help='Specific indicator ID to validate',
        )
        parser.add_argument(
            '--output-json',
            action='store_true',
            help='Output results in JSON format',
        )

    def handle(self, *args, **options):
        indicator_id = options.get('indicator')
        
        if indicator_id:
            try:
                indicator = Indicador.objects.get(id=indicator_id, activo=True)
                self.stdout.write(f'Running validations for indicator: {indicator.nombre}')
            except Indicador.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Indicator {indicator_id} not found or inactive')
                )
                return
        else:
            self.stdout.write('Running validations for all indicators')
        
        # Execute validations
        results = run_automatic_validations(indicator_id)
        
        if options['output_json']:
            self.stdout.write(json.dumps(results, indent=2))
        else:
            # Human-readable output
            self.stdout.write(f"\n=== VALIDATION RESULTS ===")
            self.stdout.write(f"Total validations: {results['total_validations']}")
            self.stdout.write(f"Errors: {results['errors']}")
            self.stdout.write(f"Warnings: {results['warnings']}")
            self.stdout.write(f"Status: {results['status']}")
            
            self.stdout.write(f"\n=== DETAILED RESULTS ===")
            for result in results['results']:
                status_color = {
                    'success': self.style.SUCCESS,
                    'warning': self.style.WARNING,
                    'error': self.style.ERROR
                }.get(result['status'], self.style.NOTICE)
                
                self.stdout.write(
                    f"{status_color('●')} {result['type']}: {result['message']}"
                )
                if result['affected_records'] > 0:
                    self.stdout.write(f"   Affected records: {result['affected_records']}")
        
        # Summary
        if results['errors'] > 0:
            self.stdout.write(
                self.style.ERROR(f"\nValidation completed with {results['errors']} errors")
            )
        elif results['warnings'] > 0:
            self.stdout.write(
                self.style.WARNING(f"\nValidation completed with {results['warnings']} warnings")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("\nAll validations passed successfully!")
            )
