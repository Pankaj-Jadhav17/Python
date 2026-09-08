type ExampleComponentProps = {
  title?: string;
};

export default function ExampleComponent({ title = 'Example Component' }: ExampleComponentProps) {
  return (
    <section style={{ border: '1px solid #ddd', padding: '1rem', borderRadius: '8px', marginTop: '1rem' }}>
      <h2>{title}</h2>
      <p>This is a sample component inside the frontend components folder.</p>
    </section>
  );
}
