declare module "mammoth/mammoth.browser" {
  const mammoth: {
    extractRawText(input: { arrayBuffer: ArrayBuffer }): Promise<{
      value?: string;
      messages?: Array<{ message?: string }>;
    }>;
  };

  export default mammoth;
}
